"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, BookOpen, Check, ChevronRight, ExternalLink, Highlighter, ImagePlus, List, LoaderCircle, LogOut, Mic, MoreHorizontal, PenLine, Pencil, Plus, Search, ShieldCheck, Trash2, X } from "@/lib/icons";

type User = { id: string; email: string };
type Source = { url: string; title: string };
type Picture = { url: string; thumbnail: string; sourceUrl: string; caption: string; license: string; attribution: string };
type Annotation = { start: number; end: number; color: "yellow" | "red" };
type Entry = { id: string; title: string; content: string; category: string; subcategory: string; createdAt: string; updatedAt: string; sources: Source[]; images: Picture[]; annotations: Annotation[] };
type Fact = { id: string; text: string; section: string; sourceUrl: string };
type Research = { title: string; category: string; subcategory: string; sourceUrl: string; facts: Fact[]; images: Picture[]; error?: string };
type Pen = "selection" | "yellow" | "red";
type Notice = { kind: "success" | "error"; text: string };
type Pending = { kind: "search" | "save"; content: string; entryId?: string };
type ResearchGroup = { entry: Entry | null; queue: Promise<void>; seen: Set<string>; pending: number };
type IllustrationState = { content: string; phase: "loading" | "ready" | "unavailable" };
type Recognition = { lang: string; continuous: boolean; interimResults: boolean; onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null; onend: (() => void) | null; onerror: ((event: { error: string }) => void) | null; start: () => void; stop: () => void };
type RecognitionConstructor = new () => Recognition;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init, headers: { ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers } });
  const data: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const problem = data as { error?: string | { message?: string }; message?: string };
    throw new Error((typeof problem.error === "string" ? problem.error : problem.message || problem.error?.message) || "Something went wrong. Please try again.");
  }
  return data as T;
}
function errorMessage(error: unknown) { return error instanceof Error ? error.message : "Something went wrong. Please try again."; }
function safeLink(value: string) { try { const url = new URL(value); return url.protocol === "https:" ? url.href : undefined; } catch { return undefined; } }
function sourceName(value: string) { try { const host = new URL(value).hostname; return /(^|\.)wikipedia\.org$/.test(host) ? "Wikipedia" : host.replace(/^www\./, ""); } catch { return "Original source"; } }
function isWikipedia(value: string) { return sourceName(value) === "Wikipedia"; }
function dateLabel(value: string) { return new Date(value).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" }); }
function newGroup(): ResearchGroup { return { entry: null, queue: Promise.resolve(), seen: new Set(), pending: 0 }; }

function selectedSpan(element: HTMLElement) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return null;
  const raw = range.toString(), text = raw.trim();
  if (!text) return null;
  const prefix = range.cloneRange();
  prefix.selectNodeContents(element); prefix.setEnd(range.startContainer, range.startOffset);
  const start = prefix.toString().length + raw.indexOf(text);
  return { start, end: start + text.length, text };
}

function selectedResearchSpan(element: HTMLElement) {
  const single = selectedSpan(element);
  if (single) return single;
  const selection = window.getSelection(), container = element.closest(".research-facts");
  if (!selection?.rangeCount || selection.isCollapsed || !container) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null;
  const fragments: string[] = [];
  for (const paragraph of container.querySelectorAll(".research-fact p")) {
    if (!range.intersectsNode(paragraph)) continue;
    const part = document.createRange();
    part.selectNodeContents(paragraph);
    if (paragraph.contains(range.startContainer)) part.setStart(range.startContainer, range.startOffset);
    if (paragraph.contains(range.endContainer)) part.setEnd(range.endContainer, range.endOffset);
    const text = part.toString().trim();
    if (text) fragments.push(text);
  }
  const text = fragments.join("\n\n");
  return text ? { start: 0, end: text.length, text } : null;
}

function MarkedText({ content, annotations }: { content: string; annotations: Annotation[] }) {
  const marks = annotations.filter((mark) => mark.start >= 0 && mark.end <= content.length && mark.end > mark.start);
  const bounds = [...new Set([0, content.length, ...marks.flatMap((mark) => [mark.start, mark.end])])].sort((a, b) => a - b);
  return bounds.slice(0, -1).map((start, index) => {
    const end = bounds[index + 1], covering = marks.filter((mark) => mark.start <= start && mark.end >= end);
    const red = covering.some((mark) => mark.color === "red"), yellow = covering.some((mark) => mark.color === "yellow");
    return red || yellow ? <mark key={start} className={`${yellow ? "mark-yellow" : ""} ${red ? "mark-red" : ""}`}>{content.slice(start, end)}</mark> : <span key={start}>{content.slice(start, end)}</span>;
  });
}

function IconButton({ label, children, className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return <button type="button" aria-label={label} title={label} className={`icon-button ${className}`} {...props}>{children}</button>;
}
function PenTools({ pen, onChange }: { pen: Pen; onChange: (pen: Pen) => void }) {
  return <div className="pen-tools" role="group" aria-label="Pens">
    <IconButton label="Selection pen — select research text to save" className={`pen-selection ${pen === "selection" ? "is-active" : ""}`} aria-pressed={pen === "selection"} onClick={() => onChange("selection")}><PenLine size={18} /></IconButton>
    <IconButton label="Highlighter — mark saved text" className={`pen-yellow ${pen === "yellow" ? "is-active" : ""}`} aria-pressed={pen === "yellow"} onClick={() => onChange("yellow")}><Highlighter size={18} /></IconButton>
    <IconButton label="Red pen — underline saved text" className={`pen-red ${pen === "red" ? "is-active" : ""}`} aria-pressed={pen === "red"} onClick={() => onChange("red")}><Pencil size={18} /></IconButton>
  </div>;
}
function PictureCard({ picture, onKeep, kept }: { picture: Picture; onKeep?: () => void; kept?: boolean }) {
  const [failed, setFailed] = useState(false);
  return <figure className="picture-card"><div className="picture-frame">
    {failed ? <span className="image-unavailable">Image unavailable</span> : <img src={safeLink(picture.thumbnail || picture.url)} alt={picture.caption || "Reference image"} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />}
    {onKeep ? <IconButton label={kept ? "Image saved" : "Keep this image"} className={`image-keep ${kept ? "is-kept" : ""}`} disabled={kept} onClick={onKeep}>{kept ? <Check size={16} /> : <ImagePlus size={16} />}</IconButton> : null}
  </div><figcaption><a href={safeLink(picture.sourceUrl)} target="_blank" rel="noreferrer">{picture.caption || "Wikimedia Commons"}<ExternalLink size={10} /></a><span>{picture.license || "See source for license"}{picture.attribution ? ` · ${picture.attribution}` : ""}</span></figcaption></figure>;
}

function AuthDialog({ mode, setMode, onClose, onSuccess }: { mode: "signin" | "signup"; setMode: (mode: "signin" | "signup") => void; onClose: () => void; onSuccess: (user: User) => Promise<void> }) {
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const modalRef = useRef<HTMLDivElement>(null), mountedRef = useRef(true);
  useEffect(() => { mountedRef.current = true; return () => { mountedRef.current = false; }; }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await request(`/api/auth/${mode === "signup" ? "sign-up" : "sign-in"}/email`, { method: "POST", body: JSON.stringify({ email: email.trim(), password, ...(mode === "signup" ? { name: email.trim().split("@")[0].slice(0, 80) || "Reader" } : {}) }) });
      if (!mountedRef.current) return;
      const session = await request<{ user: User | null }>("/api/session");
      if (!mountedRef.current) return;
      if (!session.user) throw new Error("Could not open your session. Please sign in again.");
      await onSuccess(session.user);
    } catch (caught) { if (mountedRef.current) setError(errorMessage(caught)); } finally { if (mountedRef.current) setBusy(false); }
  }
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}><div ref={modalRef} className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-heading" onKeyDown={(event) => {
    if (event.key === "Escape" && busy) { event.stopPropagation(); return; }
    if (event.key !== "Tab") return;
    const nodes = modalRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)");
    if (!nodes?.length) return;
    const first = nodes[0], last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }}>
    <IconButton label="Close" className="dialog-close" disabled={busy} onClick={onClose}><X size={20} /></IconButton><div className="auth-mark"><BookOpen size={25} strokeWidth={1.6} /></div>
    <h1 id="auth-heading">{mode === "signup" ? "Your own Little Atlas." : "Welcome back."}</h1><p>{mode === "signup" ? "A private dictionary for your discoveries." : "Sign in to continue your dictionary."}</p>
    <form onSubmit={submit}><label htmlFor="account-email">Email</label><input id="account-email" type="email" autoComplete="email" placeholder="you@example.com" required autoFocus value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} />
      <label htmlFor="account-password">Password</label><input id="account-password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder={mode === "signup" ? "At least 10 characters" : "Your password"} minLength={mode === "signup" ? 10 : undefined} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} />
      {error ? <p className="form-error" role="alert">{error}</p> : null}<button type="submit" className="primary-button auth-submit" disabled={busy}>{busy ? <LoaderCircle size={18} className="spin" /> : null}{mode === "signup" ? "Create account" : "Sign in"}{!busy ? <ArrowRight size={16} /> : null}</button>
    </form><p className="auth-switch">{mode === "signup" ? "Already have an account?" : "New to Little Atlas?"} <button type="button" disabled={busy} onClick={() => { setMode(mode === "signup" ? "signin" : "signup"); setError(""); }}>{mode === "signup" ? "Sign in" : "Create an account"}</button></p><span className="auth-privacy"><ShieldCheck size={14} />Your entries are private to your account.</span>
  </div></div>;
}

export default function AtlasClient() {
  const [user, setUser] = useState<User | null>(null), [sessionReady, setSessionReady] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]), [entriesLoading, setEntriesLoading] = useState(false), [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState(""), [editing, setEditing] = useState(false), [saving, setSaving] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false), [catalogQuery, setCatalogQuery] = useState(""), [chapter, setChapter] = useState("All entries");
  const [accountOpen, setAccountOpen] = useState(false), [authMode, setAuthMode] = useState<"signin" | "signup" | null>(null), [notice, setNotice] = useState<Notice | null>(null);
  const [researchOpen, setResearchOpen] = useState(false), [research, setResearch] = useState<Research | null>(null), [researchQuery, setResearchQuery] = useState("");
  const [researchLoading, setResearchLoading] = useState(false), [researchError, setResearchError] = useState(""), [researchSaving, setResearchSaving] = useState(false);
  const [researchEntryId, setResearchEntryId] = useState<string | null>(null);
  const [pen, setPen] = useState<Pen>("selection"), [readerMenu, setReaderMenu] = useState(false), [deleteId, setDeleteId] = useState<string | null>(null);
  const [voiceOpen, setVoiceOpen] = useState(false), [listening, setListening] = useState(false);
  const [illustrations, setIllustrations] = useState<Record<string, IllustrationState>>({});
  const textareaRef = useRef<HTMLTextAreaElement>(null), contentRef = useRef<HTMLDivElement>(null), recognitionRef = useRef<Recognition | null>(null);
  const pendingRef = useRef<Pending | null>(null), groupRef = useRef<ResearchGroup>(newGroup()), researchRequestRef = useRef(0);
  const annotationQueueRef = useRef<Promise<void>>(Promise.resolve()), currentEntriesRef = useRef(entries);
  const sessionEpochRef = useRef(0), currentUserRef = useRef(user);
  const illustrationAttemptsRef = useRef(new Set<string>()), illustrationRequestsRef = useRef(new Set<string>());
  useEffect(() => { currentEntriesRef.current = entries; currentUserRef.current = user; }, [entries, user]);
  const active = entries.find((entry) => entry.id === activeId) ?? null;
  const activeIllustration = active && illustrations[active.id]?.content === active.content ? illustrations[active.id] : undefined;
  const showError = useCallback((error: unknown) => setNotice({ kind: "error", text: errorMessage(error) }), []);
  const putEntry = useCallback((entry: Entry, epoch: number) => {
    if (epoch !== sessionEpochRef.current) return;
    // Keep queued markings in sync even before React's next render.
    currentEntriesRef.current = [entry, ...currentEntriesRef.current.filter((item) => item.id !== entry.id)];
    setEntries((previous) => [entry, ...previous.filter((item) => item.id !== entry.id)]);
  }, []);
  const findImages = useCallback(async (entry: Entry, retry = false) => {
    if (!currentUserRef.current || entry.images.length) return;
    const epoch = sessionEpochRef.current, revision = `${entry.id}:${entry.content}`;
    if (illustrationRequestsRef.current.has(revision) || (!retry && illustrationAttemptsRef.current.has(revision))) return;
    illustrationAttemptsRef.current.add(revision); illustrationRequestsRef.current.add(revision);
    setIllustrations((previous) => ({ ...previous, [entry.id]: { content: entry.content, phase: "loading" } }));
    try {
      const data = await request<{ entry: Entry; status: "ready" | "unavailable" }>(`/api/entries/${entry.id}/illustrations`, { method: "POST", body: "{}" });
      if (epoch !== sessionEpochRef.current) return;
      const current = currentEntriesRef.current.find((item) => item.id === entry.id);
      if (!current || current.content !== entry.content || data.entry.content !== entry.content) return;
      // Only merge images: an annotation or edit may have completed during the search.
      const pictures = [...current.images, ...data.entry.images.filter((picture) => !current.images.some((saved) => saved.sourceUrl === picture.sourceUrl))].slice(0, 12);
      if (pictures.length) {
        const updated = { ...current, images: pictures, updatedAt: current.updatedAt > data.entry.updatedAt ? current.updatedAt : data.entry.updatedAt };
        putEntry(updated, epoch); if (groupRef.current.entry?.id === entry.id) groupRef.current.entry = updated;
      }
      setIllustrations((previous) => ({ ...previous, [entry.id]: { content: entry.content, phase: pictures.length ? "ready" : "unavailable" } }));
    } catch {
      if (epoch === sessionEpochRef.current) setIllustrations((previous) => ({ ...previous, [entry.id]: { content: entry.content, phase: "unavailable" } }));
    } finally { if (epoch === sessionEpochRef.current) illustrationRequestsRef.current.delete(revision); }
  }, [putEntry]);
  useEffect(() => {
    if (user && active && !editing && !active.images.length) void findImages(active);
  }, [user, active, editing, findImages]);

  useEffect(() => {
    let live = true; const epoch = sessionEpochRef.current;
    request<{ user: User | null }>("/api/session").then((data) => { if (live && epoch === sessionEpochRef.current) { if (data.user) setEntriesLoading(true); setUser(data.user); } }).catch((error) => { if (live && epoch === sessionEpochRef.current) showError(error); }).finally(() => { if (live) setSessionReady(true); });
    return () => { live = false; recognitionRef.current?.stop(); };
  }, [showError]);
  useEffect(() => {
    if (!user) return;
    let live = true; const epoch = sessionEpochRef.current;
    request<{ entries: Entry[] }>("/api/entries").then((data) => { if (live && epoch === sessionEpochRef.current) setEntries((previous) => {
      const combined = new Map(data.entries.map((entry) => [entry.id, entry]));
      for (const entry of previous) if (!combined.has(entry.id) || entry.updatedAt > combined.get(entry.id)!.updatedAt) combined.set(entry.id, entry);
      return [...combined.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
    }); }).catch((error) => { if (live && epoch === sessionEpochRef.current) showError(error); }).finally(() => { if (live && epoch === sessionEpochRef.current) setEntriesLoading(false); });
    return () => { live = false; };
  }, [user, showError]);
  useEffect(() => { if (!notice || notice.kind === "error") return; const timer = window.setTimeout(() => setNotice(null), 4500); return () => window.clearTimeout(timer); }, [notice]);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "b") { event.preventDefault(); setSidebarOpen((open) => !open); }
      if (event.key === "Escape") { setSidebarOpen(false); setAccountOpen(false); setVoiceOpen(false); setReaderMenu(false); setDeleteId(null); setAuthMode(null); pendingRef.current = null; setResearchOpen(false); }
    }
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, []);

  const chapters = useMemo(() => { const counts = new Map<string, number>(); for (const entry of entries) counts.set(entry.category, (counts.get(entry.category) || 0) + 1); return [...counts].sort(([a], [b]) => a.localeCompare(b)); }, [entries]);
  const visibleEntries = useMemo(() => entries.filter((entry) => (chapter === "All entries" || entry.category === chapter) && `${entry.title} ${entry.content}`.toLowerCase().includes(catalogQuery.toLowerCase())), [entries, chapter, catalogQuery]);
  function newContent() { setActiveId(null); setEditing(false); setDraft(""); setReaderMenu(false); setSidebarOpen(false); window.setTimeout(() => textareaRef.current?.focus(), 50); }

  async function persistContent(content: string, entryId?: string) {
    if (!content.trim() || saving) return;
    const epoch = sessionEpochRef.current; setSaving(true); setNotice(null);
    try {
      const data = await request<{ entry: Entry }>(entryId ? `/api/entries/${entryId}` : "/api/entries", { method: entryId ? "PATCH" : "POST", body: JSON.stringify({ content }) });
      if (epoch !== sessionEpochRef.current) return;
      putEntry(data.entry, epoch); if (groupRef.current.entry?.id === data.entry.id) groupRef.current.entry = data.entry;
      setActiveId(data.entry.id); setEditing(false); setDraft(""); setNotice({ kind: "success", text: "Saved and organized." });
      if (!data.entry.images.length) void findImages(data.entry);
    } catch (error) { if (epoch === sessionEpochRef.current) showError(error); }
    finally { if (epoch === sessionEpochRef.current) setSaving(false); }
  }
  function saveContent() {
    if (!draft.trim()) return; const entryId = editing ? activeId || undefined : undefined;
    if (!user) { pendingRef.current = { kind: "save", content: draft, entryId }; setAuthMode("signup"); return; }
    void persistContent(draft, entryId);
  }
  async function doResearch(query: string) {
    const id = ++researchRequestRef.current, epoch = sessionEpochRef.current;
    setResearchOpen(true); setResearchLoading(true); setResearchError(""); setResearch(null); setResearchQuery(query); setPen("selection"); setNotice(null); setResearchSaving(false); setResearchEntryId(null); groupRef.current = newGroup();
    try {
      const data = await request<Research>("/api/research", { method: "POST", body: JSON.stringify({ content: query }) });
      if (id !== researchRequestRef.current || epoch !== sessionEpochRef.current) return;
      setResearch(data); if (data.error) setResearchError(data.error); else if (!data.facts.length) setResearchError("No article found. Try a more specific topic.");
    } catch (error) { if (id === researchRequestRef.current && epoch === sessionEpochRef.current) setResearchError(errorMessage(error)); }
    finally { if (id === researchRequestRef.current && epoch === sessionEpochRef.current) setResearchLoading(false); }
  }
  function searchContent(query: string) {
    if (!query.trim()) return;
    if (query.length > 30000) { setNotice({ kind: "error", text: "Content can contain up to 30,000 characters." }); return; }
    if (!user) { pendingRef.current = { kind: "search", content: query }; setAuthMode("signup"); return; }
    void doResearch(query);
  }
  async function signedIn(account: User) {
    sessionEpochRef.current++;
    illustrationAttemptsRef.current.clear(); illustrationRequestsRef.current.clear(); setIllustrations({});
    if (currentUserRef.current?.id !== account.id) { setEntries([]); currentEntriesRef.current = []; setActiveId(null); setResearch(null); setResearchOpen(false); setResearchEntryId(null); groupRef.current = newGroup(); }
    currentUserRef.current = account; setEntriesLoading(true); setUser(account); setSessionReady(true); setAuthMode(null);
    const pending = pendingRef.current; pendingRef.current = null;
    if (pending?.kind === "search") await doResearch(pending.content);
    else if (pending?.kind === "save") await persistContent(pending.content, pending.entryId);
  }
  async function signOut() {
    setAccountOpen(false); sessionEpochRef.current++; researchRequestRef.current++; recognitionRef.current?.stop();
    illustrationAttemptsRef.current.clear(); illustrationRequestsRef.current.clear(); setIllustrations({});
    try {
      await request("/api/auth/sign-out", { method: "POST", body: "{}" });
      currentUserRef.current = null; currentEntriesRef.current = []; pendingRef.current = null;
      setUser(null); setEntries([]); setActiveId(null); setDraft(""); setEditing(false); setResearch(null); setResearchOpen(false); setResearchEntryId(null); setSidebarOpen(false); setNotice(null); setSaving(false); setResearchSaving(false); setEntriesLoading(false); setResearchLoading(false); setListening(false); groupRef.current = newGroup();
    }
    catch (error) { showError(error); }
  }
  function keepPassage(element: HTMLElement, fact: Fact) {
    const span = selectedResearchSpan(element); if (!span || !research || span.text.length < 2) return;
    if (pen !== "selection") { setNotice({ kind: "error", text: "Use the selection pen to keep a passage. Highlight and underline in your saved entry." }); return; }
    const group = groupRef.current, key = `${fact.id}:${span.start}:${span.end}:${span.text}`, result = research, epoch = sessionEpochRef.current;
    if (group.seen.has(key)) { window.getSelection()?.removeAllRanges(); return; }
    group.seen.add(key); group.pending++; setResearchSaving(true); window.getSelection()?.removeAllRanges();
    group.queue = group.queue.then(async () => {
      if (epoch !== sessionEpochRef.current) return;
      try {
        const previous = group.entry, source = { title: result.title, url: fact.sourceUrl || result.sourceUrl };
        const sources = previous?.sources.some((item) => item.url === source.url) ? previous.sources : [...(previous?.sources || []), source];
        const data = await request<{ entry: Entry }>(previous ? `/api/entries/${previous.id}` : "/api/entries", { method: previous ? "PATCH" : "POST", body: JSON.stringify({ content: previous ? `${previous.content}\n\n${span.text}` : span.text, sources, images: previous?.images || result.images.slice(0, 2), annotations: previous?.annotations || [] }) });
        if (epoch !== sessionEpochRef.current) return;
        group.entry = data.entry; putEntry(data.entry, epoch); if (group === groupRef.current) { setResearchEntryId(data.entry.id); setActiveId(data.entry.id); setEditing(false); setDraft(""); } setNotice({ kind: "success", text: "Passage saved." });
      } catch (error) { group.seen.delete(key); if (epoch === sessionEpochRef.current) showError(error); }
      finally { group.pending--; if (group === groupRef.current && epoch === sessionEpochRef.current) setResearchSaving(group.pending > 0); }
    });
  }
  function keepPicture(picture: Picture) {
    const group = groupRef.current, epoch = sessionEpochRef.current;
    if (!group.entry) { setNotice({ kind: "error", text: "Keep a passage first. Its images will appear with your entry." }); return; }
    group.queue = group.queue.then(async () => { const entry = group.entry; if (!entry || epoch !== sessionEpochRef.current || entry.images.some((image) => image.sourceUrl === picture.sourceUrl)) return;
      try { const data = await request<{ entry: Entry }>(`/api/entries/${entry.id}`, { method: "PATCH", body: JSON.stringify({ images: [...entry.images, picture] }) }); if (epoch !== sessionEpochRef.current) return; group.entry = data.entry; putEntry(data.entry, epoch); setNotice({ kind: "success", text: "Image saved." }); } catch (error) { if (epoch === sessionEpochRef.current) showError(error); }
    });
  }
  function markSelection() {
    if (!active || pen === "selection" || !contentRef.current) return; const span = selectedSpan(contentRef.current); if (!span) return;
    const id = active.id, epoch = sessionEpochRef.current, mark: Annotation = { start: span.start, end: span.end, color: pen }; window.getSelection()?.removeAllRanges();
    const applyMark = async () => { const entry = currentEntriesRef.current.find((item) => item.id === id); if (!entry || epoch !== sessionEpochRef.current || entry.annotations.some((item) => item.start === mark.start && item.end === mark.end && item.color === mark.color)) return;
      try { const data = await request<{ entry: Entry }>(`/api/entries/${id}`, { method: "PATCH", body: JSON.stringify({ annotations: [...entry.annotations, mark] }) }); if (epoch !== sessionEpochRef.current) return; putEntry(data.entry, epoch); if (groupRef.current.entry?.id === id) groupRef.current.entry = data.entry; } catch (error) { if (epoch === sessionEpochRef.current) showError(error); }
    };
    if (groupRef.current.entry?.id === id) groupRef.current.queue = groupRef.current.queue.then(applyMark);
    else annotationQueueRef.current = annotationQueueRef.current.then(applyMark);
  }
  async function clearMarkings() {
    if (!active) return; const epoch = sessionEpochRef.current; setReaderMenu(false);
    try { const data = await request<{ entry: Entry }>(`/api/entries/${active.id}`, { method: "PATCH", body: JSON.stringify({ annotations: [] }) }); if (epoch !== sessionEpochRef.current) return; putEntry(data.entry, epoch); if (groupRef.current.entry?.id === active.id) groupRef.current.entry = data.entry; } catch (error) { if (epoch === sessionEpochRef.current) showError(error); }
  }
  async function deleteEntry() {
    if (!deleteId) return; const epoch = sessionEpochRef.current; setSaving(true);
    try { await request(`/api/entries/${deleteId}`, { method: "DELETE" }); if (epoch !== sessionEpochRef.current) return; setEntries((previous) => previous.filter((entry) => entry.id !== deleteId)); if (groupRef.current.entry?.id === deleteId) groupRef.current.entry = null; if (activeId === deleteId) newContent(); setDeleteId(null); setNotice({ kind: "success", text: "Entry deleted." }); }
    catch (error) { if (epoch === sessionEpochRef.current) showError(error); } finally { if (epoch === sessionEpochRef.current) setSaving(false); }
  }
  function microphone() {
    if (listening) { recognitionRef.current?.stop(); return; }
    const speechWindow = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor };
    if (!speechWindow.SpeechRecognition && !speechWindow.webkitSpeechRecognition) { setNotice({ kind: "error", text: "Voice input is not available in this browser. Try Chrome, or type your content." }); return; }
    setVoiceOpen((open) => !open);
  }
  function dictate(language: "en-US" | "zh-CN") {
    setVoiceOpen(false); const speechWindow = window as unknown as { SpeechRecognition?: RecognitionConstructor; webkitSpeechRecognition?: RecognitionConstructor }; const Constructor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition; if (!Constructor) return;
    const recognition = new Constructor(); recognitionRef.current = recognition; recognition.lang = language; recognition.continuous = false; recognition.interimResults = true; const prefix = draft.trimEnd(), epoch = sessionEpochRef.current;
    recognition.onresult = (event) => { if (epoch === sessionEpochRef.current) setDraft(`${prefix}${prefix ? " " : ""}${Array.from(event.results).map((result) => result[0].transcript).join(" ")}`.slice(0, 30000)); };
    recognition.onend = () => { if (epoch === sessionEpochRef.current) setListening(false); }; recognition.onerror = (event) => { if (epoch !== sessionEpochRef.current) return; setListening(false); showError(new Error(event.error === "not-allowed" ? "Allow microphone access to use dictation." : event.error === "no-speech" ? "No speech heard. Try again." : "Dictation stopped. Please try again.")); };
    try { recognition.start(); setListening(true); } catch (error) { showError(error); }
  }
  function searchDraft() { const field = textareaRef.current; searchContent(field && field.selectionStart !== field.selectionEnd ? draft.slice(field.selectionStart, field.selectionEnd).trim() : draft.trim()); }

  return <div className="atlas-app">
    <header className="app-header"><button type="button" className="brand" aria-label="Little Atlas — new entry" onClick={newContent}><span className="brand-icon"><BookOpen size={21} strokeWidth={1.8} /></span><span>Little Atlas</span></button><div className="header-actions">
      <button type="button" className={`contents-button ${sidebarOpen ? "is-active" : ""}`} aria-label="Contents" aria-expanded={sidebarOpen} aria-controls="contents-panel" onClick={() => { setSidebarOpen((open) => !open); setAccountOpen(false); }}><List size={18} /><span>Contents</span></button><span className="header-divider" />
      {!sessionReady ? <span className="session-spinner" aria-label="Loading account"><LoaderCircle size={19} className="spin" /></span> : user ? <div className="account-control"><button type="button" className="avatar" title={user.email} aria-label="Account" aria-expanded={accountOpen} onClick={() => setAccountOpen((open) => !open)}>{user.email[0].toUpperCase()}</button>{accountOpen ? <div className="popover account-popover"><span className="account-email">{user.email}</span><span className="account-private"><ShieldCheck size={13} />Private dictionary</span><button type="button" onClick={() => void signOut()}><LogOut size={15} />Sign out</button></div> : null}</div> : <button type="button" className="signin-button" onClick={() => setAuthMode("signin")}>Sign in<ArrowRight size={15} /></button>}
    </div></header>

    {sidebarOpen ? <><button type="button" className="drawer-backdrop" aria-label="Close contents" onClick={() => setSidebarOpen(false)} /><aside className="contents-panel" id="contents-panel" aria-label="Contents"><div className="contents-heading"><h2>Contents</h2><IconButton label="Close contents" onClick={() => setSidebarOpen(false)}><X size={19} /></IconButton></div><div className="catalog-search"><Search size={16} /><input type="search" aria-label="Search your entries" placeholder="Find in your dictionary" value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} /></div><button type="button" className="new-entry-button" onClick={newContent}><Plus size={17} />New entry</button>
      {user ? <><nav className="chapters" aria-label="Chapters"><button type="button" className={chapter === "All entries" ? "is-current" : ""} onClick={() => setChapter("All entries")}><BookOpen size={15} /><span>All entries</span><small>{entries.length}</small></button>{chapters.map(([name, count]) => <button type="button" key={name} className={chapter === name ? "is-current" : ""} onClick={() => setChapter(name)}><span className="chapter-dot" /><span>{name}</span><small>{count}</small></button>)}</nav><div className="entry-list-label">{chapter === "All entries" ? "Your entries" : chapter}</div><div className="catalog-list">{entriesLoading ? <div className="catalog-empty"><LoaderCircle size={20} className="spin" /></div> : visibleEntries.length ? visibleEntries.map((entry) => <button type="button" className={`catalog-entry ${activeId === entry.id ? "is-current" : ""}`} key={entry.id} onClick={() => { setActiveId(entry.id); setEditing(false); setDraft(""); setSidebarOpen(false); }}><span>{entry.title}</span><small>{dateLabel(entry.createdAt)}</small></button>) : <p className="catalog-empty">{catalogQuery ? "No matching entries." : "Your dictionary starts here."}</p>}</div></> : <div className="catalog-guest"><ShieldCheck size={24} /><p>Your dictionary belongs to you.</p><button type="button" className="text-button" onClick={() => setAuthMode("signup")}>Create your account<ArrowRight size={14} /></button></div>}
      <div className="contents-footer"><ShieldCheck size={13} />Only you can see your entries</div>
    </aside></> : null}

    <main className={`workspace ${researchOpen ? "with-research" : ""} ${!active && !editing ? "new-workspace" : ""}`}><div className={`writing-space ${active && !editing ? "has-entry" : ""}`}>
      {active && !editing ? <article className="entry-reader"><div className="entry-topline"><div className="entry-chapter"><span>{active.category}</span><ChevronRight size={12} /><span>{active.subcategory}</span></div><IconButton label="Write a new entry" onClick={newContent}><Plus size={19} /></IconButton></div><h1>{active.title}</h1><div className="entry-tools-row"><span className="entry-date">{dateLabel(active.createdAt)}</span><div className="entry-tools"><PenTools pen={pen} onChange={setPen} /><span className="tool-divider" /><IconButton label="Research this entry" disabled={researchLoading} onClick={() => searchContent(active.content)}><Search size={17} /></IconButton><IconButton label="Edit content" onClick={() => { setDraft(active.content); setEditing(true); }}><Pencil size={17} /></IconButton><div className="reader-menu-control"><IconButton label="Entry options" aria-expanded={readerMenu} onClick={() => setReaderMenu((open) => !open)}><MoreHorizontal size={19} /></IconButton>{readerMenu ? <div className="popover reader-popover"><button type="button" disabled={!active.annotations.length} onClick={() => void clearMarkings()}><Highlighter size={15} />Clear markings</button><button type="button" className="destructive" onClick={() => { setDeleteId(active.id); setReaderMenu(false); }}><Trash2 size={15} />Delete entry</button></div> : null}</div></div></div>
        <div ref={contentRef} className={`entry-copy pen-cursor-${pen}`} onMouseUp={markSelection} onTouchEnd={() => window.setTimeout(markSelection, 100)} onKeyUp={(event) => { if (event.key === "Shift") markSelection(); }} tabIndex={0} aria-label="Saved content"><MarkedText content={active.content} annotations={active.annotations} /></div>
        {active.images.length ? <div className="entry-images">{active.images.map((picture) => <PictureCard key={picture.sourceUrl} picture={picture} />)}</div> : <div className="entry-image-status" aria-live="polite">{!activeIllustration || activeIllustration.phase === "loading" ? <><LoaderCircle size={14} className="spin" /><span>Finding reference images…</span></> : <button type="button" onClick={() => void findImages(active, true)}><ImagePlus size={14} />Find images</button>}</div>}
        {active.sources.length ? <footer className="entry-sources"><h2>Sources</h2>{active.sources.map((source) => <a key={source.url} href={safeLink(source.url)} target="_blank" rel="noreferrer">{source.title || sourceName(source.url)}<ExternalLink size={12} /></a>)}<p>{active.sources.some((source) => isWikipedia(source.url)) ? <>Wikipedia excerpts: <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noreferrer">CC BY-SA 4.0</a>. </> : null}{active.sources.some((source) => !isWikipedia(source.url)) ? "Other text retains the original source's copyright. " : null}{active.images.length ? "Image licenses are shown with each image." : null}</p></footer> : null}
      </article> : <div className="composer-stage">{editing ? <button type="button" className="back-button" onClick={() => { setEditing(false); setDraft(""); }}><ArrowLeft size={16} />Back to entry</button> : null}
        <section className={`composer ${editing ? "composer-editing" : ""}`} aria-label={editing ? "Edit content" : "New content"}><textarea ref={textareaRef} aria-label="Content" placeholder="Write what you learned…" value={draft} maxLength={30000} readOnly={listening} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if ((event.metaKey || event.ctrlKey) && event.key === "Enter") { event.preventDefault(); saveContent(); } }} />
          <div className="composer-bottom"><div className="voice-control"><IconButton label={listening ? "Stop dictation" : "Dictate content"} className={listening ? "is-listening" : ""} onClick={microphone}><Mic size={20} /></IconButton>{voiceOpen ? <div className="popover voice-popover"><span className="popover-caption">Dictation language</span><button type="button" onClick={() => dictate("en-US")}>English</button><button type="button" onClick={() => dictate("zh-CN")}>Chinese</button></div> : null}{listening ? <span className="listening-label"><span />Listening</span> : <span className="composer-language">English or Chinese</span>}</div><div className="composer-actions"><IconButton label="Research this topic" className="search-action" disabled={!draft.trim() || saving} onClick={searchDraft}><Search size={20} /></IconButton><IconButton label={editing ? "Save changes" : "Save and organize content"} className="save-action" disabled={!draft.trim() || saving} onClick={saveContent}>{saving ? <LoaderCircle size={20} className="spin" /> : editing ? <Check size={21} /> : <Plus size={23} />}</IconButton></div></div>
        </section><div className="composer-footnote"><span><ShieldCheck size={13} />{user ? "Private to you" : "Your own space for what you learn"}</span><span className="keyboard-hint"><kbd>⌘ / Ctrl</kbd><kbd>↵</kbd> to save</span></div>{!user && sessionReady ? <button type="button" className="create-account-link" onClick={() => setAuthMode("signup")}>Create your dictionary<ArrowRight size={15} /></button> : null}
        {user && entries.length > 0 && !researchOpen ? <section className="recent-entries" aria-label="Recent entries"><div className="recent-heading"><h2>Recently added</h2><button type="button" className="text-button" onClick={() => setSidebarOpen(true)}>View all<ArrowRight size={13} /></button></div>{entries.slice(0, 3).map((entry) => <button type="button" className="recent-entry" key={entry.id} onClick={() => { setActiveId(entry.id); setDraft(""); }}><span className="recent-entry-icon"><BookOpen size={17} /></span><span><strong>{entry.title}</strong><small>{entry.category}</small></span><ChevronRight size={16} /></button>)}</section> : null}
      </div>}
    </div>

    {researchOpen ? <aside className="research-panel" aria-label="Research"><div className="research-top"><span><Search size={16} />Research</span><div className="research-top-actions"><a className="google-link" href={`https://www.google.com/search?q=${encodeURIComponent(researchQuery)}`} target="_blank" rel="noreferrer" title="Broaden this search on Google">Google<ExternalLink size={11} /></a><IconButton label="Close research" onClick={() => setResearchOpen(false)}><X size={18} /></IconButton></div></div><form className="research-query" onSubmit={(event) => { event.preventDefault(); searchContent(researchQuery.trim()); }}><input aria-label="Research topic" placeholder="A topic, passage, or article URL" value={researchQuery} maxLength={30000} onChange={(event) => setResearchQuery(event.target.value)} /><IconButton label="Search topic" disabled={researchLoading || !researchQuery.trim()} onClick={() => searchContent(researchQuery.trim())}><Search size={17} /></IconButton></form>
      {researchLoading ? <div className="research-loading"><LoaderCircle size={24} className="spin" /><h2>Finding your topic</h2><p>Looking for English sources and reference images.</p><div className="research-skeleton"><i /><i /><i /><i /></div></div> : researchError ? <div className="research-error"><Search size={24} /><h2>Try another topic</h2><p>{researchError}</p><button type="button" className="text-button" onClick={() => void doResearch(researchQuery)}>Try again<ArrowRight size={14} /></button></div> : research ? <><div className="research-title-row"><div><span className="research-category">{research.category}</span><h2>{research.title}</h2></div><a className="source-link icon-button" aria-label="Read original article" title="Read original article" href={safeLink(research.sourceUrl)} target="_blank" rel="noreferrer"><ExternalLink size={17} /></a></div><div className="research-pen-row"><PenTools pen={pen} onChange={setPen} /><span aria-live="polite">{researchSaving ? <><LoaderCircle className="spin" size={13} />Saving passage</> : <><span className="selection-indicator" />Select to keep</>}</span></div>
        <div className={`research-facts pen-cursor-${pen}`}>{research.facts.map((fact, index) => <section className="research-fact" key={fact.id}><div className="fact-meta"><span>{fact.section || "Overview"}</span><span>{String(index + 1).padStart(2, "0")}</span></div><p onMouseUp={(event) => keepPassage(event.currentTarget, fact)} onTouchEnd={(event) => { const element = event.currentTarget; window.setTimeout(() => keepPassage(element, fact), 100); }} onKeyUp={(event) => { if (event.key === "Shift") keepPassage(event.currentTarget, fact); }} tabIndex={0}>{fact.text}</p></section>)}</div>
        {research.images.length ? <section className="research-images"><h3>Reference images</h3><div>{research.images.map((picture) => <PictureCard key={picture.sourceUrl} picture={picture} onKeep={() => keepPicture(picture)} kept={Boolean(entries.find((entry) => entry.id === researchEntryId)?.images.some((image) => image.sourceUrl === picture.sourceUrl))} />)}</div></section> : null}<footer className="research-attribution"><a href={safeLink(research.sourceUrl)} target="_blank" rel="noreferrer">Source: {sourceName(research.sourceUrl)}<ExternalLink size={11} /></a><span>{isWikipedia(research.sourceUrl) ? <>Text: <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noreferrer">CC BY-SA 4.0</a></> : "Text retains its original source's copyright"} · No AI tokens used</span></footer>
      </> : null}
    </aside> : null}</main>

    {notice ? <div className={`notice notice-${notice.kind}`} role={notice.kind === "error" ? "alert" : "status"}>{notice.kind === "success" ? <Check size={16} /> : null}<span>{notice.text}</span><IconButton label="Dismiss message" onClick={() => setNotice(null)}><X size={15} /></IconButton></div> : null}
    {authMode ? <AuthDialog mode={authMode} setMode={setAuthMode} onClose={() => { setAuthMode(null); pendingRef.current = null; }} onSuccess={signedIn} /> : null}
    {deleteId ? <div className="modal-backdrop"><div className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-heading"><span className="delete-icon"><Trash2 size={23} /></span><h2 id="delete-heading">Delete this entry?</h2><p>The content and its markings will be removed from your dictionary.</p><div><button type="button" className="secondary-button" disabled={saving} onClick={() => setDeleteId(null)}>Keep entry</button><button type="button" className="danger-button" disabled={saving} onClick={() => void deleteEntry()}>{saving ? <LoaderCircle size={16} className="spin" /> : null}Delete</button></div></div></div> : null}
  </div>;
}
