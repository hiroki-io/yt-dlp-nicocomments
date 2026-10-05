import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { parse } from "acorn";
import { analyze } from "eslint-scope";

const WATCH_URL = "https://www.nicovideo.jp/watch/sm9";
const WATCH_ROUTE_PATH = "watch/:id/*";
const BUNDLE_MARKER = "commandsReplacer";
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36";
// Code of bundled libraries such as PixiJS and immer changes when the libraries update, so closures do not include it.
const LIBRARY_WORDS = ["exports", "prototype", "autoFreeze_", "useStrictShallowCopy_"];
const EXPECTED_PATH = new URL("official.json", import.meta.url);

const ROOTS = {
  nicoscriptParser: { contains: ["pizza", "forbidComment", "body"] },
  commentFilters: { contains: ["filterCommentQueue", "$fork", "owner"] },
  reverseRanges: { contains: ["reverseTimeRangesForOwner", "reverseTimeRangesForNonOwner"] },
  layerKind: { contains: ["$isVideoThread", "ai"] },
  reverseToggle: { name: "nicoScriptSafeStateUpdate" },
  layerEvents: { name: "registerLayerProcessorEvents" },
  rendererRefresh: { name: "refreshCommentsByTarget" },
  commentLayer: { kind: "class", contains: ["stagingChatManager", "slotRepository", "resetStagingStatus"] },
  layerProcessor: { kind: "class", contains: ["makeStagingSlot", "buildStagingParamsForMoving"] },
  stagingChats: { kind: "class", contains: ["getStagingChatList", "lastChatIndexForMoving"] },
  slotRepository: { kind: "class", contains: ["getOldestStaging", "reservedList"] },
};

const CONSTANTS = {
  colors: { contains: ["niconicowhite", "#cccc99"] },
  basicColors: { contains: ["white", "black"], excludes: ["niconicowhite", "#ffffff"] },
  premiumColors: { contains: ["niconicowhite"], excludes: ["#cccc99"] },
  positions: { contains: ["ue", "naka", "shita"] },
  resizeLineCounts: { contains: ["big", "medium", "small"], excludes: ["LINE_COUNT_FOR_CHARACTER_SIZE"] },
  lineCounts: { contains: ["LINE_COUNT_FOR_CHARACTER_SIZE", "7.8"] },
  fonts: { contains: ["defont", "gothic", "mincho"] },
  scriptNames: { contains: ["ピザ", "デフォルト", "置換", "逆"] },
  scriptTargets: { contains: ["全", "コメ", "投コメ"] },
};

async function fetchText(url) {
  for (let attempt = 1; ; attempt++) {
    try {
      const response = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
      if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
      return await response.text();
    } catch (error) {
      if (attempt >= 3) throw error;
      await new Promise((resolve) => setTimeout(resolve, 5000 * attempt));
    }
  }
}

function walk(node, visit, parent = null) {
  visit(node, parent);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) {
      for (const child of value) if (child && typeof child.type === "string") walk(child, visit, node);
    } else if (value && typeof value.type === "string") {
      walk(value, visit, node);
    }
  }
}

function keyName(node) {
  if (node.type === "Identifier" || node.type === "PrivateIdentifier") return node.name;
  if (node.type === "Literal") return String(node.value);
  return null;
}

function routeModules(manifest) {
  const ast = parse(manifest, { ecmaVersion: "latest", sourceType: "script" });
  const modules = [];
  walk(ast, (node) => {
    if (node.type !== "ObjectExpression") return;
    const props = Object.fromEntries(node.properties.map((p) => [keyName(p.key), p.value]));
    if (props.path?.value !== WATCH_ROUTE_PATH) return;
    for (const value of [props.module, ...(props.imports?.elements ?? [])]) {
      if (value?.type === "BinaryExpression" && value.right.type === "Literal") modules.push(value.right.value);
    }
  });
  return modules;
}

async function fetchBundle() {
  const html = await fetchText(WATCH_URL);
  const manifestUrl = html.match(/https:\/\/[^"]+\/assets\/manifest-[\w-]+\.js/)?.[0];
  if (!manifestUrl) throw new Error("the watch page does not reference a route manifest");
  const publicPath = manifestUrl.replace(/\/assets\/[^/]+$/, "");
  const modules = routeModules(await fetchText(manifestUrl));
  if (!modules.length) throw new Error(`the manifest does not contain the ${WATCH_ROUTE_PATH} route`);
  for (const path of modules) {
    const source = await fetchText(publicPath + path);
    if (source.includes(BUNDLE_MARKER)) return { name: path.split("/").pop(), source };
  }
  throw new Error(`no module of the watch route contains ${BUNDLE_MARKER}`);
}

class Bundle {
  constructor(source) {
    this.source = source;
    this.tokens = [];
    this.ast = parse(source, { ecmaVersion: "latest", sourceType: "module", ranges: true, onToken: this.tokens });
    this.parents = new Map();
    this.units = [];
    this.unitNodes = new Set();
    walk(this.ast, (node, parent) => {
      this.parents.set(node, parent);
      const name = this.unitName(node, parent);
      if (name === null) return;
      this.units.push({ node, name });
      this.unitNodes.add(node);
    });
    this.wordPositions = new Map();
    for (const token of this.tokens) {
      const word = ["name", "string", "template", "num"].includes(token.type.label) ? String(token.value) : null;
      if (word === null) continue;
      if (!this.wordPositions.has(word)) this.wordPositions.set(word, []);
      this.wordPositions.get(word).push(token.start);
    }
    this.variables = new Map();
    const scopes = analyze(this.ast, { ecmaVersion: 2022, sourceType: "module" });
    for (const scope of scopes.scopes) {
      for (const variable of scope.variables) {
        for (const identifier of variable.identifiers) this.variables.set(identifier.start, variable);
      }
      for (const reference of scope.references) {
        if (reference.resolved) this.variables.set(reference.identifier.start, reference.resolved);
      }
    }
  }

  unitName(node, parent) {
    switch (node.type) {
      case "VariableDeclarator":
      case "FunctionDeclaration":
      case "ClassDeclaration":
        return node.id?.name ?? null;
      case "MethodDefinition":
      case "PropertyDefinition":
        return [node.kind === "get" || node.kind === "set" ? node.kind : null, keyName(node.key)]
          .filter(Boolean)
          .join(" ");
      case "Property":
        return /Function/.test(node.value.type) ? keyName(node.key) : null;
      case "AssignmentExpression":
        return node.left.type === "MemberExpression" && !node.left.computed ? keyName(node.left.property) : null;
      case "ExpressionStatement":
        return parent?.type === "Program" ? "<statement>" : null;
      default:
        return null;
    }
  }

  containsWord(node, word) {
    const positions = this.wordPositions.get(word) ?? [];
    let low = 0;
    let high = positions.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (positions[middle] < node.start) low = middle + 1;
      else high = middle;
    }
    return low < positions.length && positions[low] < node.end;
  }

  find({ kind, name, contains = [], excludes = [] }, label, accept = () => true) {
    const candidates = this.units.filter(
      (unit) =>
        accept(unit.node) &&
        (kind !== "class" || unit.node.type === "ClassDeclaration" || unit.node.init?.type === "ClassExpression") &&
        (name === undefined || unit.name === name) &&
        contains.every((word) => this.containsWord(unit.node, word)) &&
        !excludes.some((word) => this.containsWord(unit.node, word)),
    );
    if (!candidates.length) throw new Error(`${label}: no code matches the anchor`);
    const size = (unit) => unit.node.end - unit.node.start;
    candidates.sort((a, b) => size(a) - size(b));
    if (candidates.length > 1 && size(candidates[0]) === size(candidates[1])) {
      throw new Error(`${label}: more than one piece of code matches the anchor`);
    }
    return candidates[0].node;
  }

  tokensIn(node) {
    let low = 0;
    let high = this.tokens.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (this.tokens[middle].start < node.start) low = middle + 1;
      else high = middle;
    }
    const tokens = [];
    for (let i = low; i < this.tokens.length && this.tokens[i].end <= node.end; i++) tokens.push(this.tokens[i]);
    return tokens;
  }

  enclosingUnit(node) {
    let current = this.parents.get(node);
    while (current && !this.unitNodes.has(current)) current = this.parents.get(current);
    return current;
  }

  isLibrary(node) {
    return LIBRARY_WORDS.some((word) => this.containsWord(node, word));
  }

  definitionUnits(variable) {
    const units = [];
    for (const def of variable.defs) {
      if (["Variable", "FunctionName", "ClassName"].includes(def.type)) units.push(def.node);
    }
    for (const reference of variable.references) {
      const { identifier } = reference;
      if (!reference.isWrite() || units.some((unit) => unit.start <= identifier.start && identifier.end <= unit.end)) {
        continue;
      }
      const unit = this.enclosingUnit(identifier);
      if (unit) units.push(unit);
    }
    return units;
  }

  normalize(node, names) {
    return this.tokensIn(node)
      .map((token) => {
        const variable = token.type.label === "name" ? this.variables.get(token.start) : undefined;
        if (!variable) return this.source.slice(token.start, token.end);
        if (!names.has(variable)) names.set(variable, `$${names.size}`);
        return names.get(variable);
      })
      .join(" ");
  }

  closure(root) {
    const units = [];
    const seen = new Set();
    const visit = (node) => {
      if (seen.has(node)) return;
      seen.add(node);
      units.push(node);
      for (const token of this.tokensIn(node)) {
        const variable = token.type.label === "name" ? this.variables.get(token.start) : undefined;
        if (!variable) continue;
        for (const unit of this.definitionUnits(variable)) {
          if (!(node.start <= unit.start && unit.end <= node.end) && !this.isLibrary(unit)) visit(unit);
        }
      }
    };
    visit(root);
    return units;
  }

  fingerprint(root) {
    const names = new Map();
    const units = this.closure(root).map((node) => ({
      text: this.normalize(node, new Map()),
      linked: this.normalize(node, names),
    }));
    return {
      hash: sha256(units.map((unit) => unit.linked).join("\n")),
      units: units.map((unit) => sha256(unit.text)),
      texts: units.map((unit) => unit.text),
    };
  }

  isLiteral(node) {
    try {
      return node !== null && (this.literal(node), true);
    } catch {
      return false;
    }
  }

  literal(node) {
    switch (node.type) {
      case "Literal":
        return node.regex ? `/${node.regex.pattern}/${node.regex.flags}` : node.value;
      case "UnaryExpression":
        if (node.operator === "-") return -this.literal(node.argument);
        break;
      case "TemplateLiteral":
        if (!node.expressions.length) return node.quasis[0].value.cooked;
        break;
      case "ObjectExpression":
        return Object.fromEntries(node.properties.map((p) => [keyName(p.key), this.literal(p.value)]));
      case "ArrayExpression":
        return node.elements.map((element) => this.literal(element));
      case "MemberExpression":
        if (!node.computed && node.object.type === "Identifier") return node.property.name;
        break;
      default:
        break;
    }
    throw new Error(`unsupported constant expression ${node.type} at ${node.start}`);
  }
}

function sha256(text) {
  return createHash("sha256").update(text).digest("hex");
}

function extract(source) {
  const bundle = new Bundle(source);
  const fingerprints = {};
  for (const [label, anchor] of Object.entries(ROOTS)) {
    fingerprints[label] = bundle.fingerprint(bundle.find(anchor, label));
  }
  const constants = {};
  for (const [label, anchor] of Object.entries(CONSTANTS)) {
    const isTable = (node) => node.init?.type === "ObjectExpression" && bundle.isLiteral(node.init);
    const node = bundle.find(anchor, label, isTable);
    constants[label] = bundle.literal(node.init);
  }
  return { fingerprints, constants };
}

function compare(expected, actual) {
  const problems = [];
  for (const [label, value] of Object.entries(actual.constants)) {
    const [before, after] = [JSON.stringify(expected.constants[label]), JSON.stringify(value)];
    if (before !== after) problems.push(`constant ${label} changed:\n  expected ${before}\n  actual   ${after}`);
  }
  for (const [label, fingerprint] of Object.entries(actual.fingerprints)) {
    const known = expected.fingerprints[label];
    if (known?.hash === fingerprint.hash) continue;
    const lines = [`code of ${label} changed`];
    const knownUnits = new Set(known?.units ?? []);
    fingerprint.units.forEach((hash, i) => {
      if (!knownUnits.has(hash)) lines.push(`  new or changed code:\n    ${fingerprint.texts[i].slice(0, 4000)}`);
    });
    const removed = (known?.units ?? []).filter((hash) => !fingerprint.units.includes(hash)).length;
    if (removed) lines.push(`  ${removed} piece(s) of known code are no longer used`);
    problems.push(lines.join("\n"));
  }
  return problems;
}

async function main() {
  const [command = "check", bundlePath] = process.argv.slice(2);
  if (!["check", "update"].includes(command)) throw new Error("usage: player.mjs check|update [bundle.js]");
  const bundle = bundlePath
    ? { name: bundlePath.split("/").pop(), source: await readFile(bundlePath, "utf8") }
    : await fetchBundle();
  const actual = extract(bundle.source);
  console.log(`bundle: ${bundle.name}`);
  if (command === "update") {
    const fingerprints = Object.fromEntries(
      Object.entries(actual.fingerprints).map(([label, { hash, units }]) => [label, { hash, units }]),
    );
    await writeFile(EXPECTED_PATH, `${JSON.stringify({ constants: actual.constants, fingerprints }, null, 2)}\n`);
    return;
  }
  const problems = compare(JSON.parse(await readFile(EXPECTED_PATH, "utf8")), actual);
  for (const problem of problems) console.log(`\n${problem}`);
  if (problems.length) process.exitCode = 1;
  else console.log("no changes");
}

await main();
