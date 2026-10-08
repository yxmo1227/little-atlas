import test from "node:test";
import assert from "node:assert/strict";
import { classifyContent, deriveResearchTopic, researchImages, researchTopic } from "../lib/knowledge.ts";

test("content alone creates a title and chapter while preserving paragraphs", () => {
  assert.deepEqual(classifyContent("  Erebus is the Greek personification of darkness.\r\n\r\n\r\n  He is the offspring of Chaos.  "), {
    title: "Erebus", category: "Myths & Beliefs", subcategory: "Greek Mythology",
    body: "Erebus is the Greek personification of darkness.\n\nHe is the offspring of Chaos.",
  });
});

test("Chinese input is organized without inventing an English translation", () => {
  const organized = classifyContent("生理盐水是氯化钠和水的混合物。");
  assert.equal(organized.title, "生理盐水");
  assert.equal(organized.category, "Human Body & Health");
  assert.equal(organized.body, "生理盐水是氯化钠和水的混合物。");
});

test("animal physiology stays in nature and generic notes do not match organ", () => {
  assert.equal(classifyContent("Octopuses have three hearts. Two pump blood to the gills and one to the body.").category, "Nature & Life");
  assert.equal(classifyContent("I organized my notes today.").category, "General");
  assert.equal(classifyContent("I learned about photosynthesis today. Plants use sunlight to make food.").title, "Photosynthesis");
  assert.equal(classifyContent("In Greek mythology, Erebus is the personification of darkness.").title, "Erebus");
});

function jsonResponse(value) { return new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } }); }

test("research includes later article sections rather than stopping at eighteen sentences", async (context) => {
  const sentences = Array.from({ length: 24 }, (_, index) => `Reference detail number ${index + 1} provides useful material for a notebook.`).join(' ');
  context.mock.method(globalThis, 'fetch', async (input) => {
    const url = new URL(input);
    if (url.hostname === 'commons.wikimedia.org') return jsonResponse({ query: { pages: [] } });
    if (url.searchParams.get('list') === 'search') return jsonResponse({ query: { search: [{ title: 'Expanded reference' }] } });
    return jsonResponse({ query: { pages: [{ title: 'Expanded reference', extract: `${sentences}\n\n== Later section ==\nThis later section should remain available for selection and notes.`, fullurl: 'https://en.wikipedia.org/wiki/Expanded_reference' }] } });
  });
  const result = await researchTopic('Expanded reference');
  assert.equal(result.error, undefined);
  assert.equal(result.facts.length, 25);
  assert.equal(result.facts.at(-1).section, 'Later section');
  assert.match(result.facts.at(-1).text, /remain available/);
});

const nyxParagraph = "In Greek mythology, Nyx is the goddess and personification of the night. In Hesiod's Theogony, she is the offspring of Chaos, and the mother of Aether (Upper Sky) and Hemera (Day) by Erebus (Darkness). By herself, she produces a brood of children which are mainly personifications of primarily negative forces. She features in a number of early cosmogonies, which place her as one of the first deities to exist. In the works of poets and playwrights, she lives at the ends of the Earth, and is often described as a black-robed goddess who drives through the sky in a chariot pulled by horses. In the Iliad, Homer relates that even Zeus fears to displease her.";

test("paragraph lookup extracts its subject in English, Chinese and bilingual notes", () => {
  assert.equal(deriveResearchTopic(nyxParagraph), "Nyx");
  assert.equal(deriveResearchTopic("Nyx is the Greek goddess of the night."), "Nyx");
  assert.equal(deriveResearchTopic("在希腊神话中，倪克斯是黑夜女神，也是卡俄斯的后代。"), "倪克斯");
  assert.equal(deriveResearchTopic("厄瑞波斯是希腊神话中黑暗的化身。"), "厄瑞波斯");
  assert.equal(deriveResearchTopic("我今天学到了倪克斯（Nyx）是希腊的黑夜女神。"), "Nyx");
  assert.equal(deriveResearchTopic("Erebus\nThe Greek personification of darkness."), "Erebus");
  assert.equal(deriveResearchTopic("Mercury (planet)"), "Mercury (planet)");
});

function licensedFile(title, description, license = "pd") {
  return { title, imageinfo: [{ mime: "image/jpeg", thumburl: `https://upload.wikimedia.org/${encodeURIComponent(title)}.jpg`, descriptionurl: `https://commons.wikimedia.org/wiki/${encodeURIComponent(title)}`, extmetadata: {
    License: { value: license }, LicenseShortName: { value: license === "pd" ? "Public domain" : license.toUpperCase() },
    ImageDescription: { value: description }, Artist: { value: "Museum collection" },
  } }] };
}

test("full Nyx paragraph searches Nyx and prefers its licensed article illustrations", async (context) => {
  const called = [];
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input); called.push(url);
    if (url.searchParams.get("list") === "search") {
      assert.equal(url.searchParams.get("srsearch"), "Nyx");
      return jsonResponse({ query: { search: [{ title: "Nyx" }] } });
    }
    if (url.hostname === "commons.wikimedia.org") {
      assert.equal(url.searchParams.get("generator"), null, "article images should avoid another broad Commons search");
      return jsonResponse({ query: { pages: [
        licensedFile("File:Nyx manuscript.jpg", "The goddess Nyx in a Greek manuscript"),
        licensedFile("File:Nyx statue.jpg", "Ancient Greek Nyx statue", "cc-by-sa-4.0"),
        licensedFile("File:Ancient vase.jpg", "Detail of ancient pottery depicting the goddess of night", "cc0"),
        licensedFile("File:Nyx cosmetics.jpg", "Nyx cosmetics artwork"),
        licensedFile("File:Nyx asteroid.jpg", "Nyx asteroid in astronomy"),
        licensedFile("File:Nyx restricted.jpg", "Greek goddess Nyx", "cc-by-nc"),
      ] } });
    }
    return jsonResponse({ query: { pages: [{ title: "Nyx", extract: nyxParagraph, fullurl: "https://en.wikipedia.org/wiki/Nyx", terms: { description: ["Greek goddess of the night"] }, pageimage: "Ancient_vase.jpg", images: [
      { title: "File:Nyx manuscript.jpg" }, { title: "File:Nyx statue.jpg" }, { title: "File:Nyx cosmetics.jpg" }, { title: "File:Nyx asteroid.jpg" }, { title: "File:Nyx restricted.jpg" },
    ] }] } });
  });
  const result = await researchTopic(nyxParagraph);
  assert.equal(result.title, "Nyx");
  assert.equal(result.error, undefined);
  assert.ok(result.facts.length > 3);
  assert.equal(result.images.length, 3);
  assert.match(result.images[0].sourceUrl, /Ancient%20vase/);
  assert.ok(result.images.every((image) => !/cosmetics|asteroid|restricted/.test(image.sourceUrl)));
  assert.equal(called.length, 3);
});

test("saved note illustration lookup fetches metadata without expanded article facts", async (context) => {
  const called = [];
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input); called.push(url);
    if (url.searchParams.get("list") === "search") return jsonResponse({ query: { search: [{ title: "Athena" }] } });
    if (url.hostname === "commons.wikimedia.org") return jsonResponse({ query: { pages: [
      licensedFile("File:Athena sculpture.jpg", "Athena in ancient Greek sculpture"),
    ] } });
    assert.ok(!url.searchParams.get("prop").includes("extracts"));
    return jsonResponse({ query: { pages: [{ title: "Athena", terms: { description: ["Greek goddess"] }, pageimage: "Athena_sculpture.jpg" }] } });
  });
  const result = await researchImages("Athena is the Greek goddess of wisdom.");
  assert.equal(result.length, 1);
  assert.equal(result[0].license, "Public domain");
  result[0].caption = "Mutated by caller";
  assert.notEqual((await researchImages("Athena is the Greek goddess of wisdom.")).at(0).caption, "Mutated by caller");
  assert.equal(called.length, 4, "metadata and contextual fallback are cached");
});

test("Chinese research follows the English language link and preserves attribution", async (context) => {
  const called = [];
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input);
    called.push(url);
    const params = url.searchParams;
    if (params.get("list") === "search") return jsonResponse({ query: { search: [{ title: "厄瑞玻斯" }] } });
    if (params.get("prop") === "langlinks|pageprops") return jsonResponse({ query: { pages: [{ title: "厄瑞玻斯", langlinks: [{ lang: "en", title: "Erebus" }] }] } });
    if (params.get("generator") === "search") return jsonResponse({ query: { pages: [
      { title: "File:Erebus mythology.jpg", index: 1, imageinfo: [{ mime: "image/jpeg", thumburl: "https://upload.wikimedia.org/wikipedia/commons/e/ee/Erebus.jpg", descriptionurl: "https://commons.wikimedia.org/wiki/File:Erebus_mythology.jpg", extmetadata: { License: { value: "pd" }, LicenseShortName: { value: "Public domain" }, Artist: { value: "<a>Example artist</a>" }, ImageDescription: { value: "Erebus in Greek mythology" } } }] },
      { title: "File:Erebus private.jpg", imageinfo: [{ mime: "image/jpeg", url: "https://upload.wikimedia.org/example.jpg", descriptionurl: "https://commons.wikimedia.org/example", extmetadata: { License: { value: "cc-by-nc" }, LicenseShortName: { value: "CC BY-NC" } } }] },
    ] } });
    return jsonResponse({ query: { pages: [{ title: "Erebus", extract: "Erebus is the personification of darkness in Greek mythology.\n\n== Family ==\nHe is described by Hesiod as an offspring of Chaos.\n\n== References ==\nThis reference should not become a selected fact.", terms: { description: ["Greek primordial deity"] }, fullurl: "https://en.wikipedia.org/wiki/Erebus" }] } });
  });
  const result = await researchTopic("我学了厄瑞波斯，是希腊神明");
  assert.equal(result.title, "Erebus");
  assert.equal(result.category, "Myths & Beliefs");
  assert.equal(result.facts.length, 2);
  assert.equal(result.facts[1].section, "Family");
  assert.ok(result.facts.every((fact) => fact.sourceUrl === "https://en.wikipedia.org/wiki/Erebus"));
  assert.equal(result.images.length, 1);
  assert.equal(result.images[0].attribution, "Example artist");
  assert.equal(called.length, 4);
  assert.equal(called[0].searchParams.get("srsearch"), "厄瑞波斯");
  const cached = await researchTopic("我学了厄瑞波斯，是希腊神明");
  cached.facts[0].text = "Changed by caller";
  assert.notEqual((await researchTopic("我学了厄瑞波斯，是希腊神明")).facts[0].text, "Changed by caller");
  assert.equal(called.length, 4, "repeat lookup uses cache instead of new requests");
});

test("empty and failed research do not replace or invent the user's content", async (context) => {
  assert.equal((await researchTopic("  ")).error, "Enter a topic to explore.");
  context.mock.method(globalThis, "fetch", async () => { throw new TypeError("fetch failed"); });
  const result = await researchTopic("a uniquely unreachable topic");
  assert.match(result.error, /Could not reach Wikipedia/);
  assert.equal(result.title, "a uniquely unreachable topic");
  assert.deepEqual(result.facts, []);
});

test("ambiguous subjects ask for context instead of selecting unrelated facts", async (context) => {
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input);
    if (url.searchParams.get("list") === "search") return jsonResponse({ query: { search: [{ title: "Mercury" }] } });
    return jsonResponse({ query: { pages: [{ title: "Mercury", extract: "Mercury has several meanings in different contexts.", pageprops: { disambiguation: "" } }] } });
  });
  const result = await researchTopic("Mercury");
  assert.match(result.error, /several meanings/);
  assert.deepEqual(result.facts, []);
});

test("normal saline uses its medical article and Commons failure keeps text", async (context) => {
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input);
    if (url.hostname === "commons.wikimedia.org") return new Response("Unavailable", { status: 503 });
    assert.equal(url.searchParams.get("titles"), "Saline (medicine)");
    return jsonResponse({ query: { pages: [{ title: "Saline (medicine)", extract: "Saline is a mixture of sodium chloride and water used in medicine.", fullurl: "https://en.wikipedia.org/wiki/Saline_(medicine)" }] } });
  });
  const result = await researchTopic("normal saline");
  assert.equal(result.category, "Human Body & Health");
  assert.equal(result.facts.length, 1);
  assert.deepEqual(result.images, []);
  assert.equal(result.error, undefined);
});
