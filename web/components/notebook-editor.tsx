"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type TextareaHTMLAttributes } from "react";
import { BookOpen, Check, List, LoaderCircle, Pencil, Plus, Search, Trash2, X } from "@/lib/icons";
import type { Annotation, Entry } from "@/lib/entry-data";
import { blocksFromContent, contentFromBlocks, type NotebookBlock } from "@/lib/notebook";
import "../app/notebook.css";

export type NotebookSavePatch = {
  content: string;
  blocks: NotebookBlock[];
  title: string;
  category: string;
  subcategory: string;
  baseRevision: number;
};

export type NotebookEditorHandle = {
  flush: () => Promise<boolean>;
  getContent: () => string;
  isDirty: () => boolean;
  exportMarkdown: () => void;
};

export type NotebookEditorProps = {
  entry: Entry;
  onSave: (patch: NotebookSavePatch) => Promise<Entry>;
  onResearch?: (content: string) => void;
  onDelete?: () => void;
  onDirtyChange?: (dirty: boolean) => void;
  onAnnotate?: (mark: Annotation) => Promise<void> | void;
  pen?: "selection" | "yellow" | "red";
  toolbar?: ReactNode;
  children?: ReactNode;
  initialEditing?: boolean;
};

type Draft = Pick<NotebookSavePatch, "blocks" | "title" | "category" | "subcategory">;
type SavePhase = "saved" | "waiting" | "saving" | "failed" | "offline" | "conflict";
type SaveError = Error & { status?: number; code?: string; entry?: Entry; currentEntry?: Entry };
const CONTENT_LIMIT = 200_000;
const BLOCK_LIMIT = 1_000;

function draftFromEntry(entry: Entry): Draft {
  return { title: entry.title, category: entry.category, subcategory: entry.subcategory,
    blocks: entry.blocks?.length ? entry.blocks.map((block) => ({ ...block })) : blocksFromContent(entry.content) };
}

function fingerprint(draft: Draft) {
  return JSON.stringify([draft.title, draft.category, draft.subcategory, draft.blocks]);
}

function newBlock(type: NotebookBlock["type"] = "paragraph", text = ""): NotebookBlock {
  return { id: crypto.randomUUID(), type, text };
}

function blockLabel(type: NotebookBlock["type"]) {
  return type === "heading1" ? "Heading" : type === "heading2" ? "Subheading" : "Paragraph";
}

function ResizeTextarea({ value, className = "", sizeKey, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { value: string; sizeKey?: string }) {
  const element = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (!element.current) return;
    element.current.style.height = "0px";
    element.current.style.height = `${element.current.scrollHeight}px`;
  }, [value, sizeKey]);
  useEffect(() => {
    const field = element.current;
    if (!field || typeof ResizeObserver === "undefined") return;
    let width = field.clientWidth;
    const observer = new ResizeObserver(() => {
      if (width === field.clientWidth) return;
      width = field.clientWidth;
      field.style.height = "0px";
      field.style.height = `${field.scrollHeight}px`;
    });
    observer.observe(field);
    return () => observer.disconnect();
  }, []);
  return <textarea {...props} ref={element} rows={1} value={value} className={className} onInput={(event) => {
    const field = event.currentTarget;
    field.style.height = "0px";
    field.style.height = `${field.scrollHeight}px`;
    props.onInput?.(event);
  }} />;
}

function MarkedBlock({ text, start, annotations }: { text: string; start: number; annotations: Annotation[] }) {
  const marks = annotations.filter((mark) => mark.end > start && mark.start < start + text.length)
    .map((mark) => ({ ...mark, start: Math.max(0, mark.start - start), end: Math.min(text.length, mark.end - start) }));
  const bounds = [...new Set([0, text.length, ...marks.flatMap((mark) => [mark.start, mark.end])])].sort((a, b) => a - b);
  return bounds.slice(0, -1).map((from, index) => {
    const to = bounds[index + 1], covering = marks.filter((mark) => mark.start <= from && mark.end >= to);
    const yellow = covering.some((mark) => mark.color === "yellow"), red = covering.some((mark) => mark.color === "red");
    return yellow || red ? <mark key={from} className={`${yellow ? "mark-yellow" : ""} ${red ? "mark-red" : ""}`}>{text.slice(from, to)}</mark> : <span key={from}>{text.slice(from, to)}</span>;
  });
}

function DownloadIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v4h14v-4" /></svg>;
}

/** A plain-text document editor. All rendering stays escaped; cloud writes are supplied by the account-aware parent. */
export const NotebookEditor = forwardRef<NotebookEditorHandle, NotebookEditorProps>(function NotebookEditor({ entry, onSave, onResearch, onDelete, onDirtyChange, onAnnotate, pen = "selection", toolbar, children, initialEditing = true }, ref) {
  const [initialDraft] = useState(() => draftFromEntry(entry)); // A different document is mounted with a different key.
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const [editing, setEditing] = useState(initialEditing);
  const [activeBlock, setActiveBlock] = useState(initialDraft.blocks[0]?.id ?? "");
  const [outlineOpen, setOutlineOpen] = useState(false), [metadataOpen, setMetadataOpen] = useState(false);
  const [phase, setPhase] = useState<SavePhase>("saved"), [problem, setProblem] = useState("");
  const [dirty, setDirty] = useState(false), [retryVersion, setRetryVersion] = useState(0);
  const [online, setOnline] = useState(true), [savedAt, setSavedAt] = useState(entry.updatedAt);
  const draftRef = useRef(draft), baseRef = useRef(entry), serverRef = useRef(entry);
  const savedFingerprint = useRef(fingerprint(initialDraft)), mounted = useRef(true), onlineRef = useRef(true);
  const conflictRef = useRef(false), inFlight = useRef<Promise<boolean> | null>(null), submittedRef = useRef<string | null>(null);
  const saveHandler = useRef(onSave), dirtyHandler = useRef(onDirtyChange);
  const documentRef = useRef<HTMLDivElement>(null), paperRef = useRef<HTMLElement>(null), focusAfterRender = useRef<string | null>(null);
  useLayoutEffect(() => { saveHandler.current = onSave; dirtyHandler.current = onDirtyChange; }, [onSave, onDirtyChange]);

  const isDirty = useCallback(() => fingerprint(draftRef.current) !== savedFingerprint.current, []);

  const updateDraft = useCallback((next: Draft | ((previous: Draft) => Draft)) => {
    const value = typeof next === "function" ? next(draftRef.current) : next;
    draftRef.current = value;
    setDraft(value);
    const changed = fingerprint(value) !== savedFingerprint.current;
    setDirty(changed);
    if (!conflictRef.current) {
      setPhase(changed ? onlineRef.current ? "waiting" : "offline" : "saved");
      setProblem("");
    }
  }, []);

  const exportMarkdown = useCallback(() => {
    const current = draftRef.current, server = serverRef.current;
    const lines = [`# ${current.title.trim() || "Untitled notebook"}`, "", `${current.category}${current.subcategory ? ` · ${current.subcategory}` : ""}`, "",
      ...current.blocks.flatMap((block) => [`${block.type === "heading1" ? "## " : block.type === "heading2" ? "### " : ""}${block.text}`, ""])];
    if (server.sources.length) lines.push("## Sources", "", ...server.sources.map((source) => `- ${source.title || source.url}: ${source.url}`), "");
    if (server.images.length) lines.push("## Reference images", "", ...server.images.flatMap((image) => [`![${image.caption.replace(/[\[\]]/g, "")} ](${image.url})`, `${image.license}${image.attribution ? ` · ${image.attribution}` : ""} · ${image.sourceUrl}`, ""]));
    const file = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(file), link = document.createElement("a");
    link.href = url; link.download = `${(current.title || "Notebook").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-").slice(0, 100)}.md`;
    document.body.appendChild(link); link.click(); link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, []);

  const flush = useCallback(async function flushDraft(): Promise<boolean> {
    if (inFlight.current) {
      const okay = await inFlight.current;
      return okay ? flushDraft() : false;
    }
    if (!isDirty()) return true;
    if (conflictRef.current) return false;
    if (!onlineRef.current) { if (mounted.current) setPhase("offline"); return false; }
    const original = draftRef.current;
    const snapshot = { ...original, title: original.title.trim(), category: original.category.trim(), subcategory: original.subcategory.trim() };
    const content = contentFromBlocks(snapshot.blocks);
    const invalid = !content.trim() ? "Write some content before saving." : !snapshot.title.trim() ? "Give this notebook a title before saving." : !snapshot.category.trim() ? "Add a category before saving." : content.length > CONTENT_LIMIT ? "Keep this notebook under 200,000 characters." : snapshot.blocks.length > BLOCK_LIMIT ? "Use up to 1,000 text blocks in one notebook." : "";
    if (invalid) { if (mounted.current) { setPhase("failed"); setProblem(invalid); } return false; }
    const submitted = fingerprint(original);
    submittedRef.current = fingerprint(snapshot);
    if (mounted.current) { setPhase("saving"); setProblem(""); }
    const operation = (async () => {
      try {
        const saved = await saveHandler.current({ ...snapshot, content, baseRevision: baseRef.current.revision });
        const savedDraft = draftFromEntry(saved), normalized = fingerprint(savedDraft);
        if (saved.id !== baseRef.current.id) throw new Error("The server returned a different notebook. Your changes have not been replaced.");
        // A newer remote version may have arrived while this request was in flight.
        if (saved.revision < baseRef.current.revision && normalized !== savedFingerprint.current) {
          conflictRef.current = true;
          if (mounted.current) { setPhase("conflict"); setProblem("This notebook changed on another device. Your unsaved changes are still here."); }
          return false;
        }
        if (saved.revision >= baseRef.current.revision) { baseRef.current = saved; serverRef.current = saved; savedFingerprint.current = normalized; }
        if (fingerprint(draftRef.current) === submitted) {
          draftRef.current = savedDraft;
          if (mounted.current) setDraft(savedDraft);
        }
        const changed = isDirty();
        if (mounted.current) { setDirty(changed); setSavedAt(saved.updatedAt); setPhase(changed ? "waiting" : "saved"); }
        return true;
      } catch (caught) {
        const error = caught as SaveError;
        if (error?.status === 409 || error?.code === "CONFLICT") {
          const remote = error.currentEntry || error.entry;
          if (remote && remote.id === baseRef.current.id) serverRef.current = remote;
          conflictRef.current = true;
          if (mounted.current) { setPhase("conflict"); setProblem("This notebook changed on another device. Your unsaved changes are still here."); }
        } else if (mounted.current) {
          setPhase(onlineRef.current ? "failed" : "offline");
          setProblem(error instanceof Error ? error.message : "Could not save. Your changes are still in this editor.");
        }
        return false;
      } finally { submittedRef.current = null; inFlight.current = null; }
    })();
    inFlight.current = operation;
    const okay = await operation;
    // A flush used before navigation also writes typing that happened during the request.
    if (okay && isDirty()) return flushDraft();
    return okay;
  }, [isDirty]);

  useImperativeHandle(ref, () => ({ flush, getContent: () => contentFromBlocks(draftRef.current.blocks), isDirty, exportMarkdown }), [flush, isDirty, exportMarkdown]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => { dirtyHandler.current?.(dirty); }, [dirty]);

  useEffect(() => {
    if (entry.id !== baseRef.current.id || entry.revision < baseRef.current.revision) return;
    serverRef.current = entry;
    const incoming = draftFromEntry(entry), incomingFingerprint = fingerprint(incoming);
    if (incomingFingerprint === savedFingerprint.current) {
      baseRef.current = entry; setSavedAt(entry.updatedAt);
      return; // Images and markings may change independently of the document draft.
    }
    if (submittedRef.current === incomingFingerprint) {
      baseRef.current = entry; savedFingerprint.current = incomingFingerprint; setSavedAt(entry.updatedAt);
      const changed = isDirty(); setDirty(changed);
      if (!changed) setPhase("saved");
      return;
    }
    if (isDirty() || inFlight.current) {
      conflictRef.current = true; setPhase("conflict");
      setProblem("This notebook changed on another device. Your unsaved changes are still here.");
      return;
    }
    baseRef.current = entry; savedFingerprint.current = incomingFingerprint; draftRef.current = incoming;
    setDraft(incoming); setSavedAt(entry.updatedAt); setDirty(false); setPhase("saved");
  }, [entry, isDirty]);

  useEffect(() => {
    if (!dirty || conflictRef.current || !online || phase === "failed") return;
    const timer = window.setTimeout(() => { void flush(); }, 900);
    return () => window.clearTimeout(timer);
  }, [draft, dirty, online, retryVersion, flush, phase]);

  useEffect(() => {
    function updateConnection() {
      const connected = navigator.onLine;
      onlineRef.current = connected; setOnline(connected);
      if (isDirty() && !conflictRef.current) { setPhase(connected ? "waiting" : "offline"); if (connected) setRetryVersion((value) => value + 1); }
    }
    updateConnection();
    window.addEventListener("online", updateConnection); window.addEventListener("offline", updateConnection);
    function warnUnsaved(event: BeforeUnloadEvent) {
      if (!isDirty()) return;
      event.preventDefault(); event.returnValue = "";
    }
    window.addEventListener("beforeunload", warnUnsaved);
    return () => { window.removeEventListener("online", updateConnection); window.removeEventListener("offline", updateConnection); window.removeEventListener("beforeunload", warnUnsaved); };
  }, [isDirty]);

  useLayoutEffect(() => {
    if (!focusAfterRender.current) return;
    const target = document.getElementById(`notebook-field-${focusAfterRender.current}`) as HTMLTextAreaElement | null;
    if (target) { target.focus({ preventScroll: true }); target.setSelectionRange(target.value.length, target.value.length); target.closest(".notebook-block")?.scrollIntoView({ block: "nearest" }); }
    focusAfterRender.current = null;
  }, [draft.blocks, editing]);

  const headingBlocks = draft.blocks.filter((block) => block.type !== "paragraph");
  const offsets = useMemo(() => {
    const starts: number[] = [];
    let offset = 0;
    for (const block of draft.blocks) { starts.push(offset); offset += block.text.length + 2; }
    return starts;
  }, [draft.blocks]);

  function jumpTo(id: string) {
    const target = id === "overview" ? paperRef.current : document.getElementById(`notebook-block-${id}`);
    target?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    if (id !== "overview") { setActiveBlock(id); if (editing) (document.getElementById(`notebook-field-${id}`) as HTMLTextAreaElement | null)?.focus({ preventScroll: true }); }
    setOutlineOpen(false);
  }

  function addBlock(type: NotebookBlock["type"]) {
    if (draftRef.current.blocks.length >= BLOCK_LIMIT) { setProblem("Use up to 1,000 text blocks in one notebook."); return; }
    const blocks = [...draftRef.current.blocks], currentIndex = blocks.findIndex((block) => block.id === activeBlock);
    const reuse = currentIndex >= 0 && !blocks[currentIndex].text.trim();
    const added = reuse ? { ...blocks[currentIndex], type } : newBlock(type);
    if (reuse) blocks[currentIndex] = added;
    else blocks.splice(currentIndex < 0 ? blocks.length : currentIndex + 1, 0, added);
    focusAfterRender.current = added.id; setActiveBlock(added.id); setEditing(true);
    updateDraft({ ...draftRef.current, blocks });
  }

  function changeText(id: string, text: string) {
    updateDraft((current) => ({ ...current, blocks: current.blocks.map((block) => block.id === id ? { ...block, text } : block) }));
  }

  function removeBlock(id: string) {
    const blocks = draftRef.current.blocks, index = blocks.findIndex((block) => block.id === id);
    const remaining = blocks.filter((block) => block.id !== id);
    if (!remaining.length) remaining.push(newBlock());
    const next = remaining[Math.max(0, index - 1)] || remaining[0];
    setActiveBlock(next.id); focusAfterRender.current = next.id;
    updateDraft({ ...draftRef.current, blocks: remaining });
  }

  function moveBlock(id: string, direction: -1 | 1) {
    const blocks = [...draftRef.current.blocks], index = blocks.findIndex((block) => block.id === id), target = index + direction;
    if (index < 0 || target < 0 || target >= blocks.length) return;
    [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
    updateDraft({ ...draftRef.current, blocks });
  }

  function annotateSelection() {
    if (editing || pen === "selection" || !onAnnotate || isDirty()) return;
    const selection = window.getSelection(), container = documentRef.current;
    if (!selection?.rangeCount || selection.isCollapsed || !container) return;
    const range = selection.getRangeAt(0);
    if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return;
    let start: number | null = null, end: number | null = null;
    for (let index = 0; index < draftRef.current.blocks.length; index++) {
      const block = draftRef.current.blocks[index], element = document.getElementById(`notebook-copy-${block.id}`);
      if (!element || !range.intersectsNode(element)) continue;
      const part = document.createRange(); part.selectNodeContents(element);
      if (element.contains(range.startContainer)) part.setStart(range.startContainer, range.startOffset);
      if (element.contains(range.endContainer)) part.setEnd(range.endContainer, range.endOffset);
      const raw = part.toString(), text = raw.trim();
      if (!text) continue;
      const prefix = part.cloneRange(); prefix.selectNodeContents(element); prefix.setEnd(part.startContainer, part.startOffset);
      const localStart = prefix.toString().length + raw.indexOf(text);
      if (start === null) start = offsets[index] + localStart;
      end = offsets[index] + localStart + text.length;
    }
    if (start === null || end === null || end <= start) return;
    const operation = onAnnotate({ start, end, color: pen });
    Promise.resolve(operation).catch((error) => setProblem(error instanceof Error ? error.message : "Could not save this marking. Please try again."));
    selection.removeAllRanges();
  }

  function reloadSaved() {
    if (isDirty() && !window.confirm("Reload the saved version? This replaces your unsaved changes. Use Export copy first if you want to keep them.")) return;
    const remote = serverRef.current, next = draftFromEntry(remote);
    baseRef.current = remote; savedFingerprint.current = fingerprint(next); conflictRef.current = false;
    draftRef.current = next; setDraft(next); setDirty(false); setPhase("saved"); setProblem(""); setSavedAt(remote.updatedAt);
  }

  const statusLabel = phase === "saving" ? "Saving…" : phase === "waiting" ? "Unsaved changes" : phase === "failed" ? "Could not save" : phase === "offline" ? "Offline · not saved" : phase === "conflict" ? "Changes need attention" : "Saved to your account";
  const activeType = draft.blocks.find((block) => block.id === activeBlock)?.type || "paragraph";
  const isPending = dirty || phase === "saving";

  return <section className={`notebook-editor ${editing ? "notebook-is-editing" : "notebook-is-reading"}`} aria-label="Notebook document">
    <div className="notebook-commandbar">
      <div className="notebook-command-left"><button type="button" className="notebook-outline-toggle" aria-label="Document outline" aria-expanded={outlineOpen} onClick={() => setOutlineOpen((value) => !value)}><List size={18} /><span>Outline</span></button>
        <div className={`notebook-save-state notebook-save-${phase}`} role="status" aria-live="polite" title={phase === "saved" ? `Saved ${new Date(savedAt).toLocaleString("en")}` : undefined}>{phase === "saving" ? <LoaderCircle size={14} className="spin" /> : phase === "saved" ? <Check size={14} /> : <span className="notebook-state-dot" />}<span>{statusLabel}</span></div>
      </div>
      <div className="notebook-command-actions">
        <button type="button" className="notebook-mode-button" aria-pressed={editing} onClick={async () => { if (editing) { if (!(await flush())) return; } setEditing((value) => !value); }}>{editing ? <BookOpen size={15} /> : <Pencil size={15} />}<span>{editing ? "Read" : "Edit"}</span></button>
        {onResearch ? <button type="button" className="notebook-icon" aria-label="Research this notebook" title="Research this notebook" onClick={async () => { if (await flush()) onResearch(contentFromBlocks(draftRef.current.blocks)); }}><Search size={17} /></button> : null}
        <button type="button" className="notebook-icon" aria-label="Export notebook as Markdown" title="Export notebook as Markdown" onClick={exportMarkdown}><DownloadIcon /></button>
        {onDelete ? <button type="button" className="notebook-icon notebook-delete" aria-label="Delete notebook" title="Delete notebook" onClick={onDelete}><Trash2 size={16} /></button> : null}
      </div>
    </div>

    {problem || phase === "offline" ? <div className={`notebook-save-message ${phase === "conflict" ? "notebook-conflict" : ""}`} role="alert"><span>{problem || "You are offline. Your changes are kept in this open editor and will save when you reconnect."}</span><div>{phase === "conflict" ? <><button type="button" onClick={exportMarkdown}>Export copy</button><button type="button" onClick={reloadSaved}>Reload saved</button></> : <>{online && isPending ? <button type="button" onClick={() => { void flush(); }}>Retry save</button> : null}<button type="button" onClick={exportMarkdown}>Export copy</button></>}</div></div> : null}

    <div className="notebook-layout">
      {outlineOpen ? <button className="notebook-outline-backdrop" type="button" aria-label="Close document outline" onClick={() => setOutlineOpen(false)} /> : null}
      <aside className={`notebook-outline ${outlineOpen ? "notebook-outline-open" : ""}`} aria-label="Document outline"><div className="notebook-outline-heading"><span>In this notebook</span><button className="notebook-icon notebook-outline-close" type="button" aria-label="Close outline" onClick={() => setOutlineOpen(false)}><X size={16} /></button></div>
        <nav><button type="button" className="notebook-outline-title" onClick={() => jumpTo("overview")}>{draft.title.trim() || "Untitled notebook"}</button>
          {headingBlocks.map((block) => <button key={block.id} type="button" className={`notebook-outline-link ${block.type === "heading2" ? "notebook-outline-subheading" : ""} ${activeBlock === block.id ? "notebook-outline-current" : ""}`} onClick={() => jumpTo(block.id)}>{block.text.trim() || "Untitled section"}</button>)}
        </nav>{!headingBlocks.length ? <p>Add headings to give your notebook an outline.</p> : null}
        <div className="notebook-outline-footnote"><span>{draft.blocks.length} {draft.blocks.length === 1 ? "block" : "blocks"}</span><span>Private notebook</span></div>
      </aside>

      <article className="notebook-paper" ref={paperRef}>
        <header className="notebook-document-heading">
          <div className="notebook-categories"><span>{draft.category || "Category"}</span>{draft.subcategory ? <><span className="notebook-category-separator">/</span><span>{draft.subcategory}</span></> : null}{editing ? <button type="button" className="notebook-icon notebook-metadata-toggle" aria-label="Edit category and subcategory" aria-expanded={metadataOpen} onClick={() => setMetadataOpen((value) => !value)}><Pencil size={13} /></button> : null}</div>
          {metadataOpen && editing ? <div className="notebook-metadata-fields"><label>Category<input aria-label="Notebook category" value={draft.category} maxLength={80} onChange={(event) => updateDraft({ ...draftRef.current, category: event.target.value })} /></label><label>Subcategory<input aria-label="Notebook subcategory" value={draft.subcategory} maxLength={120} placeholder="Optional" onChange={(event) => updateDraft({ ...draftRef.current, subcategory: event.target.value })} /></label></div> : null}
          {editing ? <ResizeTextarea className="notebook-title" aria-label="Notebook title" value={draft.title} placeholder="Untitled notebook" maxLength={120} spellCheck onChange={(event) => updateDraft({ ...draftRef.current, title: event.target.value.replace(/\n/g, " ") })} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); (document.getElementById(`notebook-field-${draft.blocks[0]?.id}`) as HTMLTextAreaElement | null)?.focus(); } }} /> : <h1 className="notebook-title">{draft.title || "Untitled notebook"}</h1>}
          <div className="notebook-document-meta"><span>{new Date(entry.createdAt).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })}</span><span>{editing ? "Editing" : "Reading"}</span></div>
        </header>

        <div className="notebook-formatbar">{editing ? <>
          <select aria-label="Text style" value={activeType} onChange={(event) => updateDraft((current) => ({ ...current, blocks: current.blocks.map((block) => block.id === activeBlock ? { ...block, type: event.target.value as NotebookBlock["type"] } : block) }))}><option value="paragraph">Paragraph</option><option value="heading1">Heading</option><option value="heading2">Subheading</option></select><span className="notebook-format-divider" />
          <button type="button" onClick={() => addBlock("heading1")} title="Add heading"><span className="notebook-format-h">H1</span><span>Heading</span></button><button type="button" onClick={() => addBlock("heading2")} title="Add subheading"><span className="notebook-format-h">H2</span><span>Subheading</span></button><button type="button" onClick={() => addBlock("paragraph")} title="Add text"><Plus size={15} /><span>Text</span></button>
        </> : toolbar || <span className="notebook-reading-label">Your saved notebook</span>}</div>

        <div className={`notebook-document-content pen-cursor-${pen}`} ref={documentRef} onPointerUp={annotateSelection} onKeyUp={(event) => { if (event.key === "Shift") annotateSelection(); }}>
          {draft.blocks.map((block, index) => <div key={block.id} id={`notebook-block-${block.id}`} className={`notebook-block notebook-block-${block.type} ${activeBlock === block.id ? "notebook-block-active" : ""}`}>
            {editing ? <><ResizeTextarea id={`notebook-field-${block.id}`} className="notebook-block-field" sizeKey={block.type} aria-label={`${blockLabel(block.type)} ${index + 1}`} placeholder={block.type === "paragraph" ? "Write your thoughts…" : "Untitled section"} value={block.text} spellCheck onFocus={() => setActiveBlock(block.id)} onChange={(event) => changeText(block.id, event.target.value)} onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); void flush(); }
              if (block.type !== "paragraph" && event.key === "Enter" && !event.shiftKey) {
                if (draftRef.current.blocks.length >= BLOCK_LIMIT) { event.preventDefault(); setProblem("Use up to 1,000 text blocks in one notebook."); return; }
                event.preventDefault(); const field = event.currentTarget, before = block.text.slice(0, field.selectionStart), after = block.text.slice(field.selectionEnd), added = newBlock("paragraph", after);
                const blocks = draftRef.current.blocks.flatMap((value) => value.id === block.id ? [{ ...value, text: before }, added] : [value]);
                focusAfterRender.current = added.id; setActiveBlock(added.id); updateDraft({ ...draftRef.current, blocks });
              }
            }} /><div className="notebook-block-actions"><button type="button" aria-label={`Move ${blockLabel(block.type).toLowerCase()} ${index + 1} up`} title="Move up" disabled={index === 0} onClick={() => moveBlock(block.id, -1)}>↑</button><button type="button" aria-label={`Move ${blockLabel(block.type).toLowerCase()} ${index + 1} down`} title="Move down" disabled={index === draft.blocks.length - 1} onClick={() => moveBlock(block.id, 1)}>↓</button><button type="button" aria-label={`Remove ${blockLabel(block.type).toLowerCase()} ${index + 1}`} title="Remove block" onClick={() => removeBlock(block.id)}><Trash2 size={13} /></button></div></> : block.type === "heading1" ? <h2 id={`notebook-copy-${block.id}`}><MarkedBlock text={block.text} start={offsets[index]} annotations={entry.annotations} /></h2> : block.type === "heading2" ? <h3 id={`notebook-copy-${block.id}`}><MarkedBlock text={block.text} start={offsets[index]} annotations={entry.annotations} /></h3> : <p id={`notebook-copy-${block.id}`}><MarkedBlock text={block.text} start={offsets[index]} annotations={entry.annotations} /></p>}
          </div>)}
        </div>
        {editing ? <button type="button" className="notebook-add-paragraph" onClick={() => { setActiveBlock(draft.blocks[draft.blocks.length - 1]?.id || ""); const added = newBlock(); focusAfterRender.current = added.id; setActiveBlock(added.id); updateDraft({ ...draftRef.current, blocks: [...draftRef.current.blocks, added] }); }} disabled={draft.blocks.length >= BLOCK_LIMIT}><Plus size={16} /><span>Add text</span></button> : null}
        {children ? <footer className="notebook-reference-material">{children}</footer> : null}
      </article>
    </div>
  </section>;
});

export default NotebookEditor;
