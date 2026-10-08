/** Automatic organization and source-linked research. No language model is called. */

export const CATEGORIES = [
  "Nature & Life", "Human Body & Health", "History & Society",
  "Language & Literature", "Myths & Beliefs", "Science & Technology",
  "Arts & Culture", "Earth & Space", "People & Places", "Everyday Life", "General",
] as const;

export type OrganizedContent = {
  title: string;
  category: string;
  subcategory: string;
  body: string;
};

export type ResearchFact = {
  id: string;
  text: string;
  section: string;
  sourceUrl: string;
};

export type ResearchImage = {
  url: string;
  thumbnail: string;
  sourceUrl: string;
  caption: string;
  license: string;
  attribution: string;
};

export type ResearchResult = {
  title: string;
  category: string;
  subcategory: string;
  sourceUrl: string;
  facts: ResearchFact[];
  images: ResearchImage[];
  error?: string;
};

type ClassificationRule = {
  category: string;
  subcategory: string;
  terms: RegExp;
  specific: RegExp;
};

const rules: ClassificationRule[] = [
  { category: "Myths & Beliefs", subcategory: "Mythology & Belief", terms: /\b(?:myth(?:s|ology|ological)?|deit(?:y|ies)|god(?:s|dess(?:es)?)?|folklore|religion|legend|underworld|cosmogon\w*)\b|神话|神明|神祇|冥界|民间传说|宗教|信仰/gi, specific: /\b(?:ereb(?:us|os)|zeus|nyx|odin|athena|hesiod|theogony)\b|厄瑞[波玻]斯|宙斯|奥丁|雅典娜/gi },
  { category: "Human Body & Health", subcategory: "Body & Medicine", terms: /\b(?:anatom\w*|physiolog\w*|disease\w*|medicine|medical|syndrome\w*|health|blood|nerves?|organs?|cells?|wounds?|saline|sodium chloride)\b|生理|医学|疾病|健康|人体|器官|血液|伤口|盐水|细胞/gi, specific: /\b(?:hypovolemi\w*|diabet\w*|neurolog\w*|heart|kidney\w*|contact lenses|normal saline|saline solution)\b|生理盐水|心脏|肾脏|神经|糖尿病/gi },
  { category: "Nature & Life", subcategory: "Living Things", terms: /\b(?:animals?|plants?|birds?|mammals?|reptiles?|insects?|botan\w*|zoolog\w*|species|ecolog\w*|fung\w*|bacteri\w*|biolog\w*|trees?|flowers?|octop(?:us|uses))\b|动物|植物|鸟类|哺乳|爬行|昆虫|生态|物种|真菌|细菌|生物|光合作用/gi, specific: /\b(?:photosynthesis|octop(?:us|uses)|penguins?|dolphins?|elephants?|orchids?|pollinat\w*|biodiversity)\b|章鱼|企鹅|海豚|大象|兰花|授粉/gi },
  { category: "Earth & Space", subcategory: "Earth & Universe", terms: /\b(?:astronom\w*|planets?|stars?|galax\w*|spacecraft|geolog\w*|volcano\w*|mountains?|oceans?|earthquake\w*|climat\w*|geograph\w*|solar|lunar|orbit\w*)\b|天文|行星|恒星|星系|太空|地质|火山|山脉|海洋|地震|气候|地理|月球|太阳系/gi, specific: /\b(?:black holes?|tectonic\w*|milky way|nebula\w*|supernova\w*)\b|黑洞|板块|银河|星云|超新星/gi },
  { category: "Language & Literature", subcategory: "Words & Works", terms: /\b(?:linguist\w*|languages?|etymolog\w*|grammar|literature|novels?|poet\w*|books?|writing system|vocabulary|pronunciation|verbs?|nouns?|adjectives?)\b|语言|词源|语法|文学|小说|诗歌|书籍|词汇|发音|动词|名词|形容词/gi, specific: /\b(?:metaphor\w*|alliterat\w*|phonem\w*|shakespeare|haiku|syntax)\b|隐喻|头韵|音素|莎士比亚|俳句|句法/gi },
  { category: "History & Society", subcategory: "History & Society", terms: /\b(?:histor\w*|civilization\w*|archaeolog\w*|politic\w*|empires?|wars?|dynast\w*|societ\w*|sociolog\w*|democrac\w*|revolution\w*)\b|历史|文明|考古|政治|帝国|战争|朝代|社会|民主|革命/gi, specific: /\b(?:renaissance|industrial revolution|roman empire|ancient egypt)\b|文艺复兴|工业革命|罗马帝国|古埃及/gi },
  { category: "Science & Technology", subcategory: "Science & Technology", terms: /\b(?:physics|chemistr\w*|mathematic\w*|technology|computers?|engineer\w*|invention\w*|scientific|algorithms?|software|electric\w*|atoms?|quantum|programming|frontend|backend|developer\w*)\b|物理|化学|数学|技术|计算机|工程|发明|科学|算法|软件|电力|原子|量子|编程|前端|后端|开发/gi, specific: /\b(?:relativity|thermodynamic\w*|javascript|python|artificial intelligence|machine learning|neural network\w*)\b|相对论|热力学|人工智能|机器学习|神经网络/gi },
  { category: "Arts & Culture", subcategory: "Arts & Culture", terms: /\b(?:painting\w*|sculptur\w*|visual art|music\w*|dance\w*|films?|cinema|architecture|theat\w*|photograph\w*|artistic|artists?|design\w*)\b|绘画|雕塑|美术|音乐|舞蹈|电影|建筑|戏剧|摄影|艺术|设计/gi, specific: /\b(?:impressionis\w*|cubis\w*|baroque|bauhaus|surrealis\w*|orchestra\w*|symphon\w*)\b|印象派|立体主义|巴洛克|包豪斯|超现实|交响/gi },
  { category: "Everyday Life", subcategory: "Daily Life", terms: /\b(?:foods?|cuisine|cooking|household|fashion|sports?|hobb(?:y|ies)|craft\w*|recipes?|coffee|tea|bread|travel\w*)\b|食物|美食|烹饪|家居|时尚|运动|爱好|手工|食谱|咖啡|茶|面包|旅行/gi, specific: /\b(?:ferment\w*|sourdough|crochet|knitting|football|basketball|tennis)\b|发酵|酸面包|钩针|编织|足球|篮球|网球/gi },
  { category: "People & Places", subcategory: "People & Places", terms: /\b(?:biograph\w*|born|cities|city|towns?|countries|country|regions?|islands?|capital|president|explorer\w*)\b|传记|出生|城市|小镇|国家|地区|岛屿|首都|总统|探险家/gi, specific: /\b(?:benjamin franklin|marie curie|nelson mandela|tokyo|sydney|paris|london)\b|富兰克林|居里|曼德拉|东京|悉尼|巴黎|伦敦/gi },
];

function inferCategory(text: string): { category: string; subcategory: string } {
  let chosen: ClassificationRule | undefined;
  let highScore = 0;
  for (const rule of rules) {
    const score = (text.match(rule.terms)?.length ?? 0) + 4 * (text.match(rule.specific)?.length ?? 0);
    if (score > highScore) {
      chosen = rule;
      highScore = score;
    }
  }
  if (!chosen) return { category: "General", subcategory: "Discoveries" };
  let subcategory = chosen.subcategory;
  if (chosen.category === "Myths & Beliefs") {
    const cultures: [RegExp, string][] = [
      [/\b(?:Greek|Erebus|Erebos|Zeus|Athena|Nyx|Hesiod)\b|希腊|厄瑞[波玻]斯|宙斯|雅典娜/i, "Greek"], [/\bRoman\b|罗马神/i, "Roman"],
      [/\bNorse\b|北欧|奥丁/i, "Norse"], [/\bEgyptian\b|埃及神/i, "Egyptian"],
      [/\bHindu\b|印度教/i, "Hindu"], [/\bChinese\b|中国神话/i, "Chinese"],
      [/\bJapanese\b|日本神话/i, "Japanese"],
    ];
    const culture = cultures.find(([pattern]) => pattern.test(text));
    if (culture) subcategory = `${culture[1]} Mythology`;
  } else if (chosen.category === "Nature & Life") {
    if (/\b(?:animal|bird|mammal|reptile|insect|octop|penguin|dolphin|elephant)\w*\b|动物|鸟类|哺乳|昆虫|章鱼|企鹅|海豚/i.test(text)) subcategory = "Animals";
    else if (/\b(?:plant|botan|flower|tree|orchid|photosynthes)\w*\b|植物|光合作用|花卉|树木/i.test(text)) subcategory = "Plants";
  }
  return { category: chosen.category, subcategory };
}

/** Preserve the user's words; titles and chapters are inferred, never supplied by a model. */
export function classifyContent(content: string): OrganizedContent {
  const body = content.replace(/\r\n?/g, "\n").split("\n")
    .map((line) => line.trim().replace(/[\t ]+/g, " ")).join("\n")
    .replace(/\n{3,}/g, "\n\n").trim();
  const firstSentence = body.split(/[\n.!?。！？]/, 1)[0]?.trim() ?? "";
  const subject = firstSentence
    .replace(/^(?:I (?:learned|read|heard)(?: today)?(?: about)?|Today I learned(?: about)?|我(?:今天|最近)?(?:学到|学了|学习了|了解了|听说了)|今天(?:学了|学到|了解到)|关于)\s*/i, "")
    .replace(/^In [^,]{1,45},\s*/i, "")
    .split(/\s+(?:is|are|was|were|refers to|means|can|has|have)\s+|是|指的是/, 1)[0]?.trim() ?? "";
  const candidate = (subject || firstSentence).replace(/^[-*#\s]+/, "").replace(/\s*\([^)]*\)/g, "").replace(/\s+(?:today|yesterday)$/i, "").trim();
  const title = /[\u3400-\u9fff]/.test(candidate)
    ? candidate.slice(0, 24)
    : candidate.split(/\s+/).slice(0, 8).join(" ").slice(0, 72);
  return { title: title ? title.charAt(0).toUpperCase() + title.slice(1) : "A new discovery", ...inferCategory(body), body };
}

const EN_API = "https://en.wikipedia.org/w/api.php";
const ZH_API = "https://zh.wikipedia.org/w/api.php";
const WIKIDATA_API = "https://www.wikidata.org/w/api.php";
const COMMONS_API = "https://commons.wikimedia.org/w/api.php";
const USER_AGENT = "LittleAtlas/0.2 (https://github.com/yxmo1227/little-atlas; source-linked personal learning)";
const MAX_RESPONSE_BYTES = 2_000_000;
const CACHE_TTL = 60 * 60 * 1000;
const cache = new Map<string, { expires: number; result: ResearchResult }>();

type Metadata = Record<string, { value?: string }>;
type WikiPage = {
  title?: string; missing?: boolean; extract?: string; fullurl?: string; pageimage?: string;
  images?: { title?: string }[];
  categories?: { title?: string }[]; terms?: { description?: string[] };
  pageprops?: Record<string, string>; langlinks?: { lang?: string; title?: string }[];
  imageinfo?: { url?: string; thumburl?: string; descriptionurl?: string; mime?: string; extmetadata?: Metadata }[];
  index?: number;
};
type WikiResponse = {
  error?: { info?: string; code?: string };
  query?: { pages?: WikiPage[]; search?: { title: string }[] };
  entities?: Record<string, { sitelinks?: { enwiki?: { title?: string } } }>;
};

async function getJson(endpoint: string, params: Record<string, string | number>): Promise<WikiResponse> {
  const url = new URL(endpoint);
  url.search = new URLSearchParams({ format: "json", formatversion: "2", ...Object.fromEntries(Object.entries(params).map(([key, value]) => [key, String(value)])) }).toString();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(url, { headers: { "User-Agent": USER_AGENT, "Accept": "application/json" }, signal: controller.signal });
    if (!response.ok) throw new Error(response.status === 429 ? "Wikipedia is busy. Please try again in a moment." : "The research service is temporarily unavailable.");
    if (Number(response.headers.get("content-length")) > MAX_RESPONSE_BYTES) throw new Error("This research response is too large.");
    const reader = response.body?.getReader();
    let payload = "";
    if (reader) {
      const decoder = new TextDecoder();
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_RESPONSE_BYTES) { await reader.cancel(); throw new Error("This research response is too large."); }
        payload += decoder.decode(value, { stream: true });
      }
      payload += decoder.decode();
    } else payload = await response.text();
    const data = JSON.parse(payload) as WikiResponse;
    if (data.error) throw new Error("The research service could not answer this request.");
    return data;
  } catch (error) {
    if (error instanceof Error && (error.name === "AbortError" || error.message === "fetch failed")) throw new Error("Could not reach Wikipedia. Your content is still here; try again shortly.");
    throw error;
  } finally { clearTimeout(timer); }
}

function normal(text: string): string { return text.toLocaleLowerCase().replace(/[^\p{L}\p{N}]/gu, ""); }

function similarity(title: string, phrase: string): number {
  const a = normal(title), b = normal(phrase);
  if (!a || !b) return 0;
  if (a === b) return 1;
  if (b.includes(a)) return 0.96;
  if (a.includes(b)) return 0.83;
  // Bounded edit distance handles transliteration differences (e.g. 厄瑞波斯 / 厄瑞玻斯).
  const x = a.slice(0, 160), y = b.slice(0, 160);
  let row = Array.from({ length: y.length + 1 }, (_, index) => index);
  for (let i = 1; i <= x.length; i++) {
    const next = [i];
    for (let j = 1; j <= y.length; j++) next[j] = Math.min(next[j - 1] + 1, row[j] + 1, row[j - 1] + (x[i - 1] === y[j - 1] ? 0 : 1));
    row = next;
  }
  return 1 - row[y.length] / Math.max(x.length, y.length);
}

/** Extract a note's subject without sending its whole paragraph to a title search. */
export function deriveResearchTopic(content: string): string {
  const raw = content.trim().replace(/[\t ]+/g, " ").slice(0, 30_000);
  const first = raw.split(/[.!?。！？\n]/, 1)[0].trim()
    .replace(/^(?:I (?:learned|read|heard)(?: today)?(?: about| that)?|Today I learned(?: about| that)?|Tell me about|What (?:is|are)|我(?:今天|最近)?(?:学了|学习了|学到了?|了解到?了?|知道了|听说了)?|今天(?:学了|学习了|学到了?|了解到?了?)|关于|请介绍|给我讲讲)\s*/i, "")
    .replace(/^In [^,]{1,60},\s*/i, "")
    .replace(/^(?:在[^，,]{1,30}|[^，,是]{1,20})(?:神话|传说|文化|文学|历史|医学)(?:中|里)[，,]?\s*/, "")
    .trim();
  const subject = first.split(/\s+(?:is|are|was|were|refers to|means|can|has|have)\s+|就是|属于|指的是|是|关于/, 1)[0].trim()
    .replace(/^(?:一个叫|一位叫|一种叫|一个|一位|一种|一只|一条|一颗|一本|个|叫做|名叫)\s*/, "")
    .replace(/^["“‘']|["”’']$/g, "").replace(/[,，;；:：]+$/, "").trim();
  // A parenthetical English name gives an unambiguous lookup for bilingual notes.
  const englishName = /[\u3400-\u9fff]/.test(subject) ? subject.match(/[（(]([A-Za-z][A-Za-z '\-]{1,70})[）)]/) : null;
  return (englishName?.[1] || subject || first || raw).slice(0, 160);
}

function searchPhrases(raw: string): string[] {
  const firstSentence = raw.split(/[.!?。！？\n]/, 1)[0].trim();
  return [...new Set([deriveResearchTopic(raw), firstSentence, raw].filter(Boolean).map((value) => value.slice(0, 160)))];
}

async function findTitle(raw: string, endpoint: string): Promise<string> {
  for (const phrase of searchPhrases(raw)) {
    const data = await getJson(endpoint, { action: "query", list: "search", srsearch: phrase, srnamespace: 0, srlimit: 12 });
    const ranked = (data.query?.search ?? []).map((item, index) => ({ title: item.title, score: similarity(item.title, phrase), index }))
      .sort((a, b) => b.score - a.score || a.index - b.index);
    if (ranked[0]?.score >= 0.65) return ranked[0].title;
  }
  throw new Error("No close article was found. Try the topic's name with a little more context.");
}

async function englishLink(title: string): Promise<string> {
  const data = await getJson(ZH_API, { action: "query", prop: "langlinks|pageprops", titles: title, redirects: 1, lllang: "en" });
  const page = data.query?.pages?.[0];
  const link = page?.langlinks?.find((item) => item.lang === "en" && item.title)?.title;
  if (link) return link;
  const item = page?.pageprops?.wikibase_item;
  if (item && /^Q[1-9]\d*$/.test(item)) {
    const entity = await getJson(WIKIDATA_API, { action: "wbgetentities", ids: item, props: "sitelinks", sitefilter: "enwiki" });
    const englishTitle = entity.entities?.[item]?.sitelinks?.enwiki?.title;
    if (englishTitle) return englishTitle;
  }
  throw new Error("This topic has no linked English article yet. Try its English name.");
}

const MAX_RESEARCH_FACTS = 300;

function splitFacts(extract: string, sourceUrl: string): ResearchFact[] {
  const facts: ResearchFact[] = [];
  const seen = new Set<string>();
  let section = "Overview";
  let skipped = false;
  for (const line of extract.slice(0, 100_000).split("\n")) {
    const heading = line.trim().match(/^(={2,6})\s*(.*?)\s*\1$/);
    if (heading) { section = heading[2] || "Overview"; skipped = /^(?:notes?|references?|sources?|citations?|bibliography|further reading|external links?|see also|footnotes?|works cited)$/i.test(section); continue; }
    if (skipped) continue;
    const paragraph = line.replace(/\s+/g, " ").trim();
    // Intl.Segmenter avoids breaking abbreviations such as "e.g." into invented fragments.
    const segments = new Intl.Segmenter("en", { granularity: "sentence" }).segment(paragraph);
    for (const part of segments) {
      const text = part.segment.trim();
      const key = normal(text);
      if (text.length < 20 || text.length > 15_000 || seen.has(key)) continue;
      seen.add(key);
      facts.push({ id: `fact-${facts.length + 1}`, text, section, sourceUrl });
      if (facts.length >= MAX_RESEARCH_FACTS) return facts;
    }
  }
  return facts;
}

function plainHtml(value: string | undefined): string {
  return (value ?? "").replace(/<[^>]*>/g, " ").replace(/&(?:amp|lt|gt|quot|apos|nbsp);/g, (entity) => ({ "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'", "&nbsp;": " " })[entity] ?? entity).replace(/\s+/g, " ").trim().slice(0, 600);
}

function metadataText(metadata: Metadata, name: string): string { return plainHtml(metadata[name]?.value); }

async function findImages(title: string, category: string, subcategory: string, article?: WikiPage): Promise<ResearchImage[]> {
  const subject = title.replace(/\s*\([^)]*\)\s*/g, " ").trim();
  const tokens = subject.toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) ?? [];
  const mainFile = article?.pageimage ? `File:${article.pageimage.replace(/_/g, " ")}` : "";
  const files = [...new Set([mainFile, ...(article?.images ?? []).map((item) => item.title ?? "")]
    .filter((file) => /\.(?:jpe?g|png|webp)$/i.test(file)))].slice(0, 10);
  const fileKey = (file: string) => file.replace(/_/g, " ").toLowerCase();
  const primaryKeys = new Set(files.map(fileKey));
  const infoParams = { prop: "imageinfo", iiprop: "url|mime|extmetadata", iiurlwidth: 900, iiextmetadatafilter: "LicenseShortName|License|ImageDescription|Categories|Artist|Credit", iiextmetadatalanguage: "en" };
  const candidates: { image: ResearchImage; score: number }[] = [];
  const seen = new Set<string>();
  const collect = (pages: WikiPage[]) => { for (const page of pages) {
    const info = page.imageinfo?.[0];
    if (!info || !["image/jpeg", "image/png", "image/webp"].includes(info.mime ?? "")) continue;
    const metadata = info.extmetadata ?? {};
    const license = metadataText(metadata, "LicenseShortName"), code = metadataText(metadata, "License").toLowerCase();
    if (!license || !(code === "pd" || code === "cc0" || /^cc-by(?:-sa)?(?:-[\d.]+)?$/.test(code) || code.startsWith("gfdl") || /^(public domain|cc0)$/i.test(license))) continue;
    const url = info.thumburl || info.url, sourceUrl = info.descriptionurl;
    if (!url?.startsWith("https://") || !sourceUrl?.startsWith("https://")) continue;
    const filename = (page.title ?? "").replace(/^File:/, "").toLowerCase();
    const description = metadataText(metadata, "ImageDescription");
    const surroundings = `${filename} ${description} ${metadataText(metadata, "Categories")}`.toLowerCase();
    const isMain = !!mainFile && fileKey(page.title ?? "") === fileKey(mainFile);
    if (!isMain && !tokens.some((token) => new RegExp(`(?:^|[^\\p{L}\\p{N}])${token}(?:$|[^\\p{L}\\p{N}])`, "u").test(surroundings))) continue;
    // Homonyms are common on Commons: a goddess's name also names brands, ships and asteroids.
    if (category === "Myths & Beliefs" && /\b(?:cosmetics?|makeup|lipsticks?|mascaras?|asteroids?|dwarf planets?|astronom\w*|galax\w*|nebula\w*|mount|volcano|antarctic|aircraft|spaceships?|mardi gras|krewe|parades?)\b|\bship\s/.test(surroundings)) continue;
    if (seen.has(sourceUrl)) continue;
    seen.add(sourceUrl);
    const score = (isMain ? 100 : primaryKeys.has(fileKey(page.title ?? "")) ? 60 : 0)
      + (filename.includes(subject.toLowerCase()) ? 10 : 0) + tokens.filter((token) => filename.includes(token)).length * 2 - (page.index ?? 99) / 100;
    candidates.push({ score, image: { url, thumbnail: url, sourceUrl, caption: description || (page.title ?? "").replace(/^File:/, "").replace(/_/g, " "), license, attribution: metadataText(metadata, "Artist") || metadataText(metadata, "Credit") || "See the original file page" } });
  } };
  if (files.length) {
    try { collect((await getJson(COMMONS_API, { action: "query", titles: files.join("|"), ...infoParams })).query?.pages ?? []); }
    catch { /* A failed metadata lookup can still fall back to subject search. */ }
  }
  if (candidates.length < 3) {
    const query = category === "Myths & Beliefs" ? `${subject} ${subcategory.toLowerCase()}` : subject;
    try { collect((await getJson(COMMONS_API, { action: "query", generator: "search", gsrsearch: query, gsrnamespace: 6, gsrlimit: 12, ...infoParams })).query?.pages ?? []); }
    catch { /* Return usable article images even if Commons search is unavailable. */ }
  }
  return candidates.sort((a, b) => b.score - a.score).slice(0, 3).map(({ image }) => image);
}

async function resolveTitle(raw: string): Promise<string> {
  const subject = deriveResearchTopic(raw);
  // These are ordinary medical synonyms, not inferred claims or model output.
  if (/^(?:normal |physiological )?saline(?: solution)?$/i.test(subject)) return "Saline (medicine)";
  const chinese = /[\u3400-\u9fff]/.test(subject);
  const title = await findTitle(raw, chinese ? ZH_API : EN_API);
  return chinese ? englishLink(title) : title;
}

const ARTICLE_METADATA = { action: "query", prop: "categories|pageterms|pageprops|info|pageimages|images", redirects: 1, cllimit: 50, wbptterms: "description", inprop: "url", piprop: "name", pilicense: "free", imlimit: 30 };

function resolvedContext(page: WikiPage, title: string): string {
  return `${title} ${(page.terms?.description ?? []).join(" ")} ${(page.categories ?? []).map((item) => item.title ?? "").join(" ")} ${page.extract?.slice(0, 1200) ?? ""}`;
}

/** Find licensed illustrations for a saved note; fetch metadata only, without expanding its text. */
export async function researchImages(content: string): Promise<ResearchImage[]> {
  const raw = content.trim().slice(0, 30_000);
  if (!raw) return [];
  const subject = deriveResearchTopic(raw);
  const key = `images:${subject.toLocaleLowerCase()}:${inferCategory(raw).category}`;
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return structuredClone(cached.result.images);
  const title = await resolveTitle(raw);
  const page = (await getJson(EN_API, { ...ARTICLE_METADATA, titles: title })).query?.pages?.[0];
  if (!page || page.missing) throw new Error("The English article is unavailable right now.");
  if (page.pageprops && "disambiguation" in page.pageprops) throw new Error("This name has several meanings. Add a few words to specify the topic.");
  const resolved = page.title || title;
  const organized = inferCategory(`${raw} ${resolvedContext(page, resolved)}`);
  const images = await findImages(resolved, organized.category, organized.subcategory, page);
  if (images.length) {
    if (cache.size >= 60) cache.delete(cache.keys().next().value as string);
    cache.set(key, { expires: Date.now() + CACHE_TTL, result: { title: resolved, ...organized, sourceUrl: "", facts: [], images: structuredClone(images) } });
  }
  return images;
}

/** Fetch English Wikipedia facts and optional freely licensed Commons images. */
export async function researchTopic(query: string): Promise<ResearchResult> {
  if (/^https?:\/\//i.test(query.trim())) return researchUrl(query.trim());
  const raw = query.trim().slice(0, 30_000);
  const empty: ResearchResult = { title: raw, ...inferCategory(raw), sourceUrl: "", facts: [], images: [] };
  if (!raw) return { ...empty, error: "Enter a topic to explore." };
  const key = raw.toLocaleLowerCase();
  const cached = cache.get(key);
  if (cached && cached.expires > Date.now()) return structuredClone(cached.result);
  try {
    let title = await resolveTitle(raw);
    let data: WikiResponse;
    const params = { ...ARTICLE_METADATA, prop: `${ARTICLE_METADATA.prop}|extracts`, titles: title, explaintext: 1, exsectionformat: "wiki" };
    try { data = await getJson(EN_API, params); }
    catch (error) { if (!(error instanceof Error) || error.message !== "This research response is too large.") throw error; data = await getJson(EN_API, { ...params, exintro: 1 }); }
    const page = data.query?.pages?.[0];
    if (!page || page.missing || !page.extract) throw new Error("The English article is unavailable right now.");
    if (page.pageprops && "disambiguation" in page.pageprops) throw new Error("This name has several meanings. Add a few words to specify the topic.");
    title = page.title || title;
    const sourceUrl = page.fullurl?.startsWith("https://en.wikipedia.org/") ? page.fullurl : `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`;
    const context = resolvedContext(page, title);
    const result: ResearchResult = { title, ...inferCategory(context), sourceUrl, facts: splitFacts(page.extract, sourceUrl), images: [] };
    if (!result.facts.length) result.error = "No useful English paragraphs were found for this topic.";
    try { result.images = await findImages(title, result.category, result.subcategory, page); } catch { /* Text still works if Commons is temporarily unavailable. */ }
    if (cache.size >= 60) cache.delete(cache.keys().next().value as string);
    cache.set(key, { expires: Date.now() + CACHE_TTL, result: structuredClone(result) });
    return result;
  } catch (error) {
    return { ...empty, error: error instanceof Error ? error.message : "Research is unavailable right now. Try again shortly." };
  }
}

const MAX_ARTICLE_BYTES = 500_000;
const publicDnsCache = new Map<string, number>();

function publicIp(address: string): boolean {
  const raw = address.replace(/^\[|\]$/g, "").toLowerCase();
  if (raw.includes(":")) return /^[23][0-9a-f]{0,3}:/.test(raw) && !raw.startsWith("2001:db8:");
  const parts = raw.split(".").map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) return false;
  const [a, b, c] = parts;
  return !(a === 0 || a === 10 || a === 127 || a >= 224 || (a === 100 && b >= 64 && b <= 127)
    || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
    || (a === 192 && (b === 168 || (b === 0 && (c === 0 || c === 2))))
    || (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100)))
    || (a === 203 && b === 0 && c === 113));
}

function articleUrl(raw: string): URL {
  let url: URL;
  try { url = new URL(raw); } catch { throw new Error("Paste a valid HTTPS article link."); }
  if (raw.length > 2048 || url.protocol !== "https:" || url.username || url.password || url.port) throw new Error("Use a public HTTPS article link without login details or a custom port.");
  const host = url.hostname.toLowerCase();
  const numericHost = /^\d+(?:\.\d+){3}$/.test(host) || host.startsWith("[");
  if ((numericHost && !publicIp(host)) || (!numericHost && (!host.includes(".") || /(?:^|\.)(?:localhost|local|internal|home|lan|test|invalid)$/.test(host)))) throw new Error("Only public article websites can be opened.");
  if ((host === "google.com" || host.endsWith(".google.com")) && /^\/(?:search|webhp)(?:\/|$)/.test(url.pathname)) throw new Error("Open an article from the search results, then paste its link here.");
  url.hash = "";
  return url;
}

async function assertPublicHost(url: URL, signal: AbortSignal): Promise<void> {
  const host = url.hostname;
  if (/^\d+(?:\.\d+){3}$/.test(host) || host.startsWith("[")) return;
  if ((publicDnsCache.get(host) ?? 0) > Date.now()) return;
  const addresses: string[] = [];
  // Web API compatible DNS checks also reject hostnames resolving to a local IP.
  for (const type of ["A", "AAAA"]) {
    const response = await fetch(`https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(host)}&type=${type}`, { headers: { Accept: "application/dns-json" }, signal });
    if (!response.ok) throw new Error("Could not verify this article website. Try another link.");
    const data = await response.json() as { Status?: number; Answer?: { type?: number; data?: string }[] };
    if (data.Status !== 0) throw new Error("This article website could not be reached.");
    for (const record of data.Answer ?? []) if ((record.type === 1 || record.type === 28) && record.data) addresses.push(record.data);
  }
  if (!addresses.length || addresses.some((address) => !publicIp(address))) throw new Error("Only public article websites can be opened.");
  if (publicDnsCache.size >= 100) publicDnsCache.delete(publicDnsCache.keys().next().value as string);
  publicDnsCache.set(host, Date.now() + 60_000);
}

function decodeEntities(value: string): string {
  return value.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (entity, name: string) => {
    if (name.startsWith("#")) {
      const code = name.toLowerCase().startsWith("#x") ? Number.parseInt(name.slice(2), 16) : Number.parseInt(name.slice(1), 10);
      return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
    }
    return ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ", ndash: "–", mdash: "—", rsquo: "’", lsquo: "‘", rdquo: "”", ldquo: "“", hellip: "…" } as Record<string, string>)[name.toLowerCase()] ?? entity;
  });
}

type ArticleText = { title: string; paragraphs: { text: string; section: string }[] };

function extractArticleHtml(html: string): ArticleText {
  const tokens = html.match(/<!--[\s\S]*?-->|<\/?[A-Za-z][^<>"']*(?:(?:"[^"]*"|'[^']*')[^<>"']*)*>|[^<]+|</g) ?? [];
  const stack: { tag: string; skip: boolean }[] = [];
  const skipTags = new Set(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "button", "svg", "table", "template", "iframe", "sup"]);
  const voidTags = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]);
  let title = "", titleParts: string[] | null = null;
  let paragraphParts: string[] | null = null, headingParts: string[] | null = null;
  let section = "Overview";
  const paragraphs: { text: string; section: string }[] = [];
  const finishParagraph = () => {
    if (!paragraphParts) return;
    const text = decodeEntities(paragraphParts.join("")).replace(/\s+/g, " ").trim();
    const letters = text.match(/\p{L}/gu) ?? [];
    const latin = text.match(/[A-Za-z]/g) ?? [];
    const boilerplate = /^(?:sign in|log in|subscribe (?:to|for)|create an account|enable javascript|accept (?:all )?cookies|please (?:sign in|log in))/i.test(text);
    if (!boilerplate && text.length >= 45 && text.length <= 6000 && latin.length / Math.max(letters.length, 1) > 0.7 && (text.match(/[A-Za-z]+/g)?.length ?? 0) >= 7) paragraphs.push({ text, section });
    paragraphParts = null;
  };
  for (const token of tokens) {
    if (token.startsWith("<!--")) continue;
    if (!token.startsWith("<")) {
      if (stack.some((node) => node.skip)) continue;
      if (titleParts) titleParts.push(token);
      if (paragraphParts) paragraphParts.push(token);
      if (headingParts) headingParts.push(token);
      continue;
    }
    const match = token.match(/^<(\/?)([a-zA-Z][\w:-]*)/);
    if (!match) continue;
    const closing = !!match[1], tag = match[2].toLowerCase();
    if (closing) {
      if (tag === "p") finishParagraph();
      if (tag === "title" && titleParts) { title = decodeEntities(titleParts.join("")).trim(); titleParts = null; }
      if (/^h[1-3]$/.test(tag) && headingParts) { section = decodeEntities(headingParts.join("")).replace(/\s+/g, " ").trim() || section; headingParts = null; }
      const index = stack.map((node) => node.tag).lastIndexOf(tag);
      if (index >= 0) stack.length = index;
      continue;
    }
    const inheritedSkip = stack.some((node) => node.skip);
    const skip = inheritedSkip || skipTags.has(tag) || /\s(?:hidden(?:\s|=|>)|aria-hidden\s*=\s*["']?true|role\s*=\s*["'](?:navigation|banner|contentinfo|complementary)["'])/i.test(token);
    if (tag === "p" && !skip) { finishParagraph(); paragraphParts = []; }
    if (tag === "title" && !skip) titleParts = [];
    if (/^h[1-3]$/.test(tag) && !skip) { finishParagraph(); headingParts = []; }
    if (tag === "br" && !skip && paragraphParts) paragraphParts.push(" ");
    if (!voidTags.has(tag) && !token.endsWith("/>")) {
      if (stack.length >= 128) throw new Error("This page's markup could not be read. Try another article source.");
      stack.push({ tag, skip });
    }
    if (paragraphs.length >= 80) break;
  }
  finishParagraph();
  return { title: title.replace(/\s*[-–—|]\s*Wikipedia$/i, "").slice(0, 150), paragraphs };
}

/** Import readable English paragraphs from a public article, without executing its HTML. */
export async function researchUrl(rawUrl: string): Promise<ResearchResult> {
  const empty: ResearchResult = { title: "Article", category: "General", subcategory: "Discoveries", sourceUrl: "", facts: [], images: [] };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);
  try {
    let url = articleUrl(rawUrl);
    const key = `url:${url.href}`;
    const cached = cache.get(key);
    if (cached && cached.expires > Date.now()) return structuredClone(cached.result);
    let html = "";
    for (let redirect = 0; redirect <= 3; redirect++) {
      await assertPublicHost(url, controller.signal);
      const response = await fetch(url, { redirect: "manual", headers: { "User-Agent": USER_AGENT, Accept: "text/html" }, signal: controller.signal });
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const location = response.headers.get("location");
        await response.body?.cancel();
        if (!location || redirect === 3) throw new Error("This article redirects too many times. Try its final link.");
        url = articleUrl(new URL(location, url).href);
        continue;
      }
      if ([401, 403].includes(response.status)) throw new Error("This article requires access or blocks automated reading. Open another public article.");
      if (!response.ok) throw new Error("This article could not be opened. Check the link or try another source.");
      if (!/^text\/html(?:;|$)|^application\/xhtml\+xml(?:;|$)/i.test(response.headers.get("content-type") ?? "")) throw new Error("Paste an article page rather than a download or other file.");
      if (Number(response.headers.get("content-length")) > MAX_ARTICLE_BYTES) throw new Error("This article page is too large to import. Try a shorter source.");
      const reader = response.body?.getReader();
      if (reader) {
        const decoder = new TextDecoder(); let size = 0;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > MAX_ARTICLE_BYTES) { await reader.cancel(); throw new Error("This article page is too large to import. Try a shorter source."); }
          html += decoder.decode(value, { stream: true });
        }
        html += decoder.decode();
      } else html = await response.text();
      break;
    }
    const extracted = extractArticleHtml(html);
    if (!extracted.paragraphs.length) throw new Error("This page has no readable English article paragraphs. Try a public article with selectable text.");
    const seen = new Set<string>();
    const facts = extracted.paragraphs.flatMap(({ text, section }) => splitFacts(text, url.href).map((fact) => ({ ...fact, section }))).filter((fact) => {
      const key = normal(fact.text); if (seen.has(key)) return false; seen.add(key); return true;
    }).slice(0, MAX_RESEARCH_FACTS).map((fact, index) => ({ ...fact, id: `fact-${index + 1}` }));
    if (!facts.length) throw new Error("This page has no useful English article sentences. Try another source.");
    const organized = classifyContent(`${extracted.title}\n${facts.map((fact) => fact.text).join("\n")}`);
    const result: ResearchResult = { title: extracted.title || organized.title, category: organized.category, subcategory: organized.subcategory, sourceUrl: url.href, facts, images: [] };
    if (cache.size >= 60) cache.delete(cache.keys().next().value as string);
    cache.set(key, { expires: Date.now() + CACHE_TTL, result: structuredClone(result) });
    return result;
  } catch (error) {
    const message = error instanceof Error && (error.name === "AbortError" || error.message === "fetch failed") ? "Could not reach this article. Try again or use another public source." : error instanceof Error ? error.message : "This article could not be imported.";
    return { ...empty, error: message };
  } finally { clearTimeout(timer); }
}
