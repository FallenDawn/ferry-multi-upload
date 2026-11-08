package ferry

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"
)

const defaultTimelineID = "00000000000000000000000000000000"

type Timeline struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	SortOrder int    `json:"sort_order"`
	CreatedAt string `json:"created_at"`
	UpdatedAt string `json:"updated_at"`
}

func (s *Store) ensureTimelineSchema(ctx context.Context) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil { return err }
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `CREATE TABLE IF NOT EXISTS timelines (
		id TEXT PRIMARY KEY, name TEXT NOT NULL, sort_order INTEGER NOT NULL,
		created_at TEXT NOT NULL, updated_at TEXT NOT NULL
	)`); err != nil { return fmt.Errorf("create timelines table: %w", err) }
	exists, err := columnExists(ctx, tx, "messages", "timeline_id")
	if err != nil { return err }
	if !exists {
		if _, err = tx.ExecContext(ctx, "ALTER TABLE messages ADD COLUMN timeline_id TEXT NOT NULL DEFAULT '"+defaultTimelineID+"'"); err != nil {
			return fmt.Errorf("add messages.timeline_id: %w", err)
		}
	}
	now := time.Now().UTC().Format(time.RFC3339Nano)
	if _, err = tx.ExecContext(ctx, `INSERT OR IGNORE INTO timelines(id,name,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)`, defaultTimelineID, "Timeline", 0, now, now); err != nil {
		return fmt.Errorf("create default timeline: %w", err)
	}
	return tx.Commit()
}

func (s *Store) ListTimelines(ctx context.Context) ([]Timeline, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT id,name,sort_order,created_at,updated_at FROM timelines ORDER BY sort_order,created_at,id")
	if err != nil { return nil, err }
	defer rows.Close()
	items := make([]Timeline, 0)
	for rows.Next() {
		var item Timeline
		if err := rows.Scan(&item.ID,&item.Name,&item.SortOrder,&item.CreatedAt,&item.UpdatedAt); err != nil { return nil, err }
		items = append(items,item)
	}
	return items, rows.Err()
}

func normalizeTimelineName(name string) (string,error) {
	name = strings.TrimSpace(name)
	if name == "" || !utf8.ValidString(name) || len(name) > 80 || strings.ContainsAny(name, "\r\n\x00") {
		return "", fmt.Errorf("%w: timeline name must be 1-80 UTF-8 bytes", ErrInvalid)
	}
	return name,nil
}

func (s *Store) CreateTimeline(ctx context.Context, name string) (Timeline,error) {
	name,err := normalizeTimelineName(name); if err != nil { return Timeline{},err }
	id,err := newID(); if err != nil { return Timeline{},err }
	now := time.Now().UTC().Format(time.RFC3339Nano)
	result,err := s.db.ExecContext(ctx,`INSERT INTO timelines(id,name,sort_order,created_at,updated_at)
		SELECT ?,?,COALESCE(MAX(sort_order),-1)+1,?,? FROM timelines`,id,name,now,now)
	if err != nil { return Timeline{},err }
	order,_ := result.RowsAffected()
	_ = order
	var sortOrder int
	if err=s.db.QueryRowContext(ctx,"SELECT sort_order FROM timelines WHERE id=?",id).Scan(&sortOrder); err != nil { return Timeline{},err }
	return Timeline{ID:id,Name:name,SortOrder:sortOrder,CreatedAt:now,UpdatedAt:now},nil
}

func (s *Store) RenameTimeline(ctx context.Context,id,name string) error {
	if id == defaultTimelineID { /* The default timeline may be renamed. */ }
	name,err := normalizeTimelineName(name); if err != nil { return err }
	now := time.Now().UTC().Format(time.RFC3339Nano)
	result,err := s.db.ExecContext(ctx,"UPDATE timelines SET name=?,updated_at=? WHERE id=?",name,now,id)
	if err != nil { return err }
	n,_ := result.RowsAffected(); if n == 0 { return ErrNotFound }; return nil
}

func (s *Store) ReorderTimelines(ctx context.Context, ids []string) error {
	items,err := s.ListTimelines(ctx); if err != nil { return err }
	if len(ids) != len(items) { return fmt.Errorf("%w: order must include every timeline",ErrInvalid) }
	known := make(map[string]bool,len(items)); for _,v := range items { known[v.ID]=true }
	tx,err := s.db.BeginTx(ctx,nil); if err != nil { return err }; defer tx.Rollback()
	now := time.Now().UTC().Format(time.RFC3339Nano)
	for i,id := range ids {
		if !known[id] { return fmt.Errorf("%w: invalid timeline order",ErrInvalid) }
		delete(known,id)
		if _,err=tx.ExecContext(ctx,"UPDATE timelines SET sort_order=?,updated_at=? WHERE id=?",i,now,id); err != nil { return err }
	}
	if len(known)!=0 { return fmt.Errorf("%w: incomplete timeline order",ErrInvalid) }
	return tx.Commit()
}

func (s *Store) DeleteTimeline(ctx context.Context,id string) error {
	if id == defaultTimelineID { return fmt.Errorf("%w: the default timeline cannot be deleted",ErrInvalid) }
	tx,err := s.db.BeginTx(ctx,nil); if err != nil { return err }; defer tx.Rollback()
	var exists int
	if err=tx.QueryRowContext(ctx,"SELECT EXISTS(SELECT 1 FROM timelines WHERE id=?)",id).Scan(&exists); err != nil { return err }
	if exists == 0 { return ErrNotFound }
	if _,err=tx.ExecContext(ctx,"UPDATE messages SET timeline_id=? WHERE timeline_id=?",defaultTimelineID,id); err != nil { return err }
	if _,err=tx.ExecContext(ctx,"DELETE FROM timelines WHERE id=?",id); err != nil { return err }
	return tx.Commit()
}

func (s *Store) TimelineExists(ctx context.Context,id string) (bool,error) {
	var exists int
	err:=s.db.QueryRowContext(ctx,"SELECT EXISTS(SELECT 1 FROM timelines WHERE id=?)",id).Scan(&exists)
	return exists==1,err
}

func (s *Store) AssignMessageTimeline(ctx context.Context,messageID,timelineID string) error {
	exists,err:=s.TimelineExists(ctx,timelineID); if err!=nil{return err}; if !exists{return ErrNotFound}
	_,err=s.db.ExecContext(ctx,"UPDATE messages SET timeline_id=? WHERE id=?",timelineID,messageID)
	return err
}

func (s *Store) ListMessagesInTimeline(ctx context.Context,timelineID string,after int64,limit int) ([]Message,int64,error) {
	rows,err:=s.db.QueryContext(ctx,`SELECT sequence,id,kind,sender_name,sender_kind,sender_device_id,text_body,file_name,media_type,file_size,blob_name,created_at
		FROM messages WHERE timeline_id=? AND sequence>? ORDER BY sequence ASC LIMIT ?`,timelineID,after,limit)
	if err!=nil{return nil,after,fmt.Errorf("query timeline messages: %w",err)}
	defer rows.Close()
	messages:=make([]Message,0); next:=after
	for rows.Next(){ message,_,scanErr:=scanMessage(rows); if scanErr!=nil{return nil,after,scanErr}; messages=append(messages,message); next=message.Sequence }
	if err=rows.Err();err!=nil{return nil,after,err}
	return messages,next,nil
}

func (s *server) listTimelines(w http.ResponseWriter,r *http.Request) {
	items,err:=s.store.ListTimelines(r.Context()); if err!=nil{s.internalError(w,err);return}
	w.Header().Set("Cache-Control","no-store"); writeJSON(w,http.StatusOK,map[string]any{"timelines":items})
}
func (s *server) createTimeline(w http.ResponseWriter,r *http.Request) {
	var body struct { Name string `json:"name"` }
	r.Body=http.MaxBytesReader(w,r.Body,maxJSONBody)
	if err:=json.NewDecoder(r.Body).Decode(&body);err!=nil{writeError(w,http.StatusBadRequest,"invalid_request","invalid timeline request");return}
	item,err:=s.store.CreateTimeline(r.Context(),body.Name);if err!=nil{s.domainError(w,err);return}
	writeJSON(w,http.StatusCreated,item)
}
func (s *server) updateTimeline(w http.ResponseWriter,r *http.Request) {
	var body struct { Name string `json:"name"` }
	r.Body=http.MaxBytesReader(w,r.Body,maxJSONBody)
	if err:=json.NewDecoder(r.Body).Decode(&body);err!=nil{writeError(w,http.StatusBadRequest,"invalid_request","invalid timeline request");return}
	err:=s.store.RenameTimeline(r.Context(),r.PathValue("timeline_id"),body.Name)
	if errors.Is(err,ErrNotFound){writeError(w,http.StatusNotFound,"not_found","timeline not found");return}
	if err!=nil{s.domainError(w,err);return};w.WriteHeader(http.StatusNoContent)
}
func (s *server) deleteTimeline(w http.ResponseWriter,r *http.Request) {
	err:=s.store.DeleteTimeline(r.Context(),r.PathValue("timeline_id"))
	if errors.Is(err,ErrNotFound){writeError(w,http.StatusNotFound,"not_found","timeline not found");return}
	if err!=nil{s.domainError(w,err);return};w.WriteHeader(http.StatusNoContent)
}
func (s *server) reorderTimelines(w http.ResponseWriter,r *http.Request) {
	var body struct { IDs []string `json:"ids"` }
	r.Body=http.MaxBytesReader(w,r.Body,maxJSONBody)
	if err:=json.NewDecoder(r.Body).Decode(&body);err!=nil{writeError(w,http.StatusBadRequest,"invalid_request","invalid timeline order");return}
	if err:=s.store.ReorderTimelines(r.Context(),body.IDs);err!=nil{s.domainError(w,err);return}
	w.WriteHeader(http.StatusNoContent)
}

var _ = sql.ErrNoRows
