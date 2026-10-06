import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { parse } from "acorn";
import type { AnyNode, Token as AcornToken } from "acorn";
import { analyze } from "eslint-scope";
import type { Variable } from "eslint-scope";

type Node = AnyNode;
type Token = AcornToken & { value?: unknown };
type Anchor = { kind?: "class"; name?: string; contains?: string[]; excludes?: string[] };
type Constant = string | number | boolean | null | Constant[] | { [key: string]: Constant };
type Fingerprint = { hash: string; units: string[]; members: string[] };
type Recorded = { bundle: string; constants: Record<string, Constant>; fingerprints: Record<string, Fingerprint> };
type Extracted = {
  constants: Record<string, Constant>;
  fingerprints: Record<string, Fingerprint & { texts: string[] }>;
};
type Table = Node & { type: "VariableDeclarator"; init: Node & { type: "ObjectExpression" } };

const WATCH_URL = "https://www.nicovideo.jp/watch/sm9";
const WATCH_ROUTE_PATH = "watch/:id/*";
const BUNDLE_MARKER = "commandsReplacer";
const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36";
// Code of bundled libraries such as PixiJS and immer changes when the libraries update, so closures do not include it.
const LIBRARY_WORDS = ["exports", "prototype", "autoFreeze_", "useStrictShallowCopy_"];
const EXPECTED_PATH = new URL("official.json", import.meta.url);
// Minification renames variables but keeps property names, so reports name the changed members.
const MEMBER_TYPES = ["MethodDefinition", "PropertyDefinition", "Property", "AssignmentExpression"];

const ROOTS: Record<string, Anchor> = {
  nicoscriptParser: { contains: ["pizza", "forbidComment", "body"] },
  commentFilters: { contains: ["filterCommentQueue", "$fork", "owner", "updatedState"] },
  reverseRanges: { contains: ["reverseTimeRangesForOwner", "reverseTimeRangesForNonOwner", "targetThreads"] },
  layerKind: { contains: ["$isVideoThread", "ai"] },
  aiCommentColor: { name: "aiCommentStagingFilter" },
  reverseToggle: { name: "nicoScriptSafeStateUpdate" },
  layerEvents: { name: "registerLayerProcessorEvents" },
  rendererRefresh: { name: "refreshCommentsByTarget" },
  commentLayer: { kind: "class", contains: ["stagingChatManager", "slotRepository", "resetStagingStatus"] },
  layerProcessor: { kind: "class", contains: ["makeStagingSlot", "buildStagingParamsForMoving"] },
  stagingChats: { kind: "class", contains: ["getStagingChatList", "lastChatIndexForMoving"] },
  slotRepository: { kind: "class", contains: ["getOldestStaging", "reservedList"] },
};

const CONSTANTS: Record<string, Anchor> = {
  colors: { contains: ["niconicowhite", "#cccc99"] },
  basicColors: { contains: ["white", "black"], excludes: ["niconicowhite", "#ffffff"] },
  premiumColors: { contains: ["niconicowhite"], excludes: ["#cccc99"] },
  positions: { contains: ["ue", "naka", "shita"] },
  resizeLineCounts: {
    contains: ["big", "medium", "small", "3", "5", "7"],
    excludes: ["LINE_COUNT_FOR_CHARACTER_SIZE"],
  },
  lineCounts: { contains: ["LINE_COUNT_FOR_CHARACTER_SIZE", "7.8"] },
  fonts: { contains: ["defont", "gothic", "mincho"] },
  scriptNames: { contains: ["ピザ", "デフォルト", "置換", "逆"] },
  scriptTargets: { contains: ["全", "コメ", "投コメ"] },
};

async function fetchText(url: string): Promise<string> {
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

function isNode(value: unknown): value is Node {
  return typeof value === "object" && value !== null && typeof (value as { type?: unknown }).type === "string";
}

function asNode(node: object): Node {
  return node as Node;
}

function walk(node: Node, visit: (node: Node, parent: Node | null) => void, parent: Node | null = null) {
  visit(node, parent);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) {
      for (const child of value) if (isNode(child)) walk(child, visit, node);
    } else if (isNode(value)) {
      walk(value, visit, node);
    }
  }
}

function keyName(node: Node): string | null {
  if (node.type === "Identifier" || node.type === "PrivateIdentifier") return node.name;
  if (node.type === "Literal") return String(node.value);
  return null;
}

function routeModules(manifest: string): string[] {
  const ast = parse(manifest, { ecmaVersion: "latest", sourceType: "script" });
  const modules: string[] = [];
  walk(ast, (node) => {
    if (node.type !== "ObjectExpression") return;
    const props = new Map<string, Node>();
    for (const p of node.properties) {
      const key = p.type === "Property" ? keyName(p.key) : null;
      if (p.type === "Property" && key !== null) props.set(key, p.value);
    }
    const path = props.get("path");
    if (path?.type !== "Literal" || path.value !== WATCH_ROUTE_PATH) return;
    const imports = props.get("imports");
    for (const value of [props.get("module"), ...(imports?.type === "ArrayExpression" ? imports.elements : [])]) {
      if (
        value?.type === "BinaryExpression" &&
        value.right.type === "Literal" &&
        typeof value.right.value === "string"
      ) {
        modules.push(value.right.value);
      }
    }
  });
  return modules;
}

async function fetchBundle(): Promise<{ name: string; source: string }> {
  const html = await fetchText(WATCH_URL);
  const manifestUrl = html.match(/https:\/\/[^"]+\/assets\/manifest-[\w-]+\.js/)?.[0];
  if (!manifestUrl) throw new Error("the watch page does not reference a route manifest");
  const publicPath = manifestUrl.replace(/\/assets\/[^/]+$/, "");
  const modules = routeModules(await fetchText(manifestUrl));
  if (!modules.length) throw new Error(`the manifest does not contain the ${WATCH_ROUTE_PATH} route`);
  for (const path of modules) {
    const source = await fetchText(publicPath + path);
    if (source.includes(BUNDLE_MARKER)) return { name: path.split("/").pop() ?? path, source };
  }
  throw new Error(`no module of the watch route contains ${BUNDLE_MARKER}`);
}

function isTable(node: Node): node is Table {
  return node.type === "VariableDeclarator" && node.init?.type === "ObjectExpression";
}

function isAny(_node: Node): _node is Node {
  return true;
}

class Bundle {
  source: string;
  tokens: Token[] = [];
  ast: Node;
  parents = new Map<Node, Node | null>();
  units: { node: Node; name: string }[] = [];
  unitNames = new Map<Node, string>();
  wordPositions = new Map<string, number[]>();
  variables = new Map<number, Variable>();

  constructor(source: string) {
    this.source = source;
    const ast = parse(source, { ecmaVersion: "latest", sourceType: "module", ranges: true, onToken: this.tokens });
    this.ast = ast;
    walk(ast, (node, parent) => {
      this.parents.set(node, parent);
      const name = this.unitName(node, parent);
      if (name === null) return;
      this.units.push({ node, name });
      this.unitNames.set(node, name);
    });
    for (const token of this.tokens) {
      const word = ["name", "string", "template", "num"].includes(token.type.label) ? String(token.value) : null;
      if (word === null) continue;
      const positions = this.wordPositions.get(word) ?? [];
      positions.push(token.start);
      this.wordPositions.set(word, positions);
    }
    const scopes = analyze(ast as unknown as Parameters<typeof analyze>[0], {
      ecmaVersion: 2022,
      sourceType: "module",
    });
    for (const scope of scopes.scopes) {
      for (const variable of scope.variables) {
        for (const identifier of variable.identifiers) this.variables.set(asNode(identifier).start, variable);
      }
      for (const reference of scope.references) {
        if (reference.resolved) this.variables.set(asNode(reference.identifier).start, reference.resolved);
      }
    }
  }

  unitName(node: Node, parent: Node | null): string | null {
    switch (node.type) {
      case "VariableDeclarator":
        return node.id.type === "Identifier" ? node.id.name : null;
      case "FunctionDeclaration":
      case "ClassDeclaration":
        return node.id?.name ?? null;
      case "MethodDefinition":
      case "PropertyDefinition":
        return [
          node.type === "MethodDefinition" && (node.kind === "get" || node.kind === "set") ? node.kind : null,
          keyName(node.key),
        ]
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

  containsWord(node: Node, word: string): boolean {
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

  isAncestor(ancestor: Node, node: Node): boolean {
    for (let current = this.parents.get(node); current; current = this.parents.get(current)) {
      if (current === ancestor) return true;
    }
    return false;
  }

  find<T extends Node>(
    { kind, name, contains = [], excludes = [] }: Anchor,
    label: string,
    accept: (node: Node) => node is T,
  ): T {
    const candidates = this.units
      .filter(
        (unit) =>
          (kind !== "class" ||
            unit.node.type === "ClassDeclaration" ||
            (unit.node.type === "VariableDeclarator" && unit.node.init?.type === "ClassExpression")) &&
          (name === undefined || unit.name === name) &&
          contains.every((word) => this.containsWord(unit.node, word)) &&
          !excludes.some((word) => this.containsWord(unit.node, word)),
      )
      .map((unit) => unit.node)
      .filter(accept);
    const innermost = candidates.filter((node) => !candidates.some((other) => this.isAncestor(node, other)));
    if (!innermost.length) throw new Error(`${label}: no code matches the anchor`);
    if (innermost.length > 1) throw new Error(`${label}: more than one piece of code matches the anchor`);
    return innermost[0];
  }

  tokensIn(node: Node): Token[] {
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

  enclosingUnit(node: Node): Node | undefined {
    let current = this.parents.get(node);
    while (current && !this.unitNames.has(current)) current = this.parents.get(current);
    return current ?? undefined;
  }

  isLibrary(node: Node): boolean {
    return LIBRARY_WORDS.some((word) => this.containsWord(node, word));
  }

  definitionUnits(variable: Variable): Node[] {
    const units: Node[] = [];
    for (const def of variable.defs) {
      if (def.type === "Variable" || def.type === "FunctionName" || def.type === "ClassName")
        units.push(asNode(def.node));
    }
    for (const reference of variable.references) {
      const identifier = asNode(reference.identifier);
      if (!reference.isWrite() || units.some((unit) => unit.start <= identifier.start && identifier.end <= unit.end)) {
        continue;
      }
      const unit = this.enclosingUnit(identifier);
      if (unit) units.push(unit);
    }
    return units;
  }

  normalize(node: Node, names: Map<Variable, string>): string {
    return this.tokensIn(node)
      .map((token) => {
        const variable = token.type.label === "name" ? this.variables.get(token.start) : undefined;
        if (!variable) return this.source.slice(token.start, token.end);
        if (!names.has(variable)) names.set(variable, `$${names.size}`);
        return names.get(variable);
      })
      .join(" ");
  }

  closure(root: Node): Node[] {
    const units: Node[] = [];
    const seen = new Set<Node>();
    const visit = (node: Node) => {
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

  fingerprint(root: Node): Fingerprint & { texts: string[] } {
    const names = new Map<Variable, string>();
    const nodes = this.closure(root);
    const units = nodes.map((node) => ({
      name: this.unitNames.get(node) ?? node.type,
      text: this.normalize(node, new Map()),
      linked: this.normalize(node, names),
    }));
    const members = nodes.flatMap((node) =>
      this.units
        .filter((unit) => unit.node !== node && node.start <= unit.node.start && unit.node.end <= node.end)
        .filter((unit) => MEMBER_TYPES.includes(unit.node.type))
        .map((unit) => entry(unit.name, this.normalize(unit.node, new Map()))),
    );
    return {
      hash: sha256(units.map((unit) => unit.linked).join("\n")),
      units: units.map((unit) => entry(unit.name, unit.text)),
      members: [...new Set(members)].sort(),
      texts: units.map((unit) => unit.text),
    };
  }

  isLiteral(node: Node): boolean {
    try {
      this.literal(node);
      return true;
    } catch {
      return false;
    }
  }

  literal(node: Node): Constant {
    switch (node.type) {
      case "Literal": {
        if (node.regex) return `/${node.regex.pattern}/${node.regex.flags}`;
        const { value } = node;
        if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
          return value;
        }
        break;
      }
      case "UnaryExpression": {
        const value = this.literal(node.argument);
        if (typeof value === "number" && node.operator === "-") return -value;
        if (typeof value === "number" && node.operator === "!") return !value;
        break;
      }
      case "TemplateLiteral": {
        const cooked = node.quasis[0].value.cooked;
        if (!node.expressions.length && typeof cooked === "string") return cooked;
        break;
      }
      case "ObjectExpression":
        return Object.fromEntries(
          node.properties.map((p) => {
            const key = p.type === "Property" && !p.computed ? keyName(p.key) : null;
            if (p.type !== "Property" || key === null) throw new Error(`unsupported object property at ${p.start}`);
            return [key, this.literal(p.value)];
          }),
        );
      case "ArrayExpression":
        return node.elements.map((element) => {
          if (!element || element.type === "SpreadElement")
            throw new Error(`unsupported array element at ${node.start}`);
          return this.literal(element);
        });
      case "MemberExpression":
        if (!node.computed && node.object.type === "Identifier" && node.property.type === "Identifier") {
          return node.property.name;
        }
        break;
      default:
        break;
    }
    throw new Error(`unsupported constant expression ${node.type} at ${node.start}`);
  }
}

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

function entry(name: string, text: string): string {
  return `${name} ${sha256(text).slice(0, 16)}`;
}

function entryName(entry: string): string {
  return entry.slice(0, entry.lastIndexOf(" "));
}

function entryHash(entry: string): string {
  return entry.slice(entry.lastIndexOf(" ") + 1);
}

function extract(source: string): Extracted {
  const bundle = new Bundle(source);
  const fingerprints: Extracted["fingerprints"] = {};
  for (const [label, anchor] of Object.entries(ROOTS)) {
    fingerprints[label] = bundle.fingerprint(bundle.find(anchor, label, isAny));
  }
  const constants: Record<string, Constant> = {};
  for (const [label, anchor] of Object.entries(CONSTANTS)) {
    const isConstantTable = (node: Node): node is Table => isTable(node) && bundle.isLiteral(node.init);
    constants[label] = bundle.literal(bundle.find(anchor, label, isConstantTable).init);
  }
  return { fingerprints, constants };
}

function compare(expected: Recorded, actual: Extracted, showCode: boolean): string[] {
  const problems = [];
  for (const [label, value] of Object.entries(actual.constants)) {
    const [before, after] = [JSON.stringify(expected.constants[label]), JSON.stringify(value)];
    if (before !== after) problems.push(`constant ${label} changed:\n  expected ${before}\n  actual   ${after}`);
  }
  for (const [label, fingerprint] of Object.entries(actual.fingerprints)) {
    const known = expected.fingerprints[label] ?? { hash: "", units: [], members: [] };
    if (known.hash === fingerprint.hash) continue;
    const lines = [`code of ${label} changed`];
    const knownHashes = new Set(known.units.map(entryHash));
    const actualHashes = new Set(fingerprint.units.map(entryHash));
    fingerprint.units.forEach((unit, i) => {
      if (knownHashes.has(entryHash(unit))) return;
      lines.push(`  new or changed code: ${entryName(unit)}`);
      if (showCode) lines.push(`    ${fingerprint.texts[i].slice(0, 4000)}`);
    });
    for (const unit of known.units) {
      if (!actualHashes.has(entryHash(unit))) lines.push(`  removed or changed code: ${entryName(unit)}`);
    }
    const knownMembers = new Set(known.members);
    const actualMembers = new Set(fingerprint.members);
    const changed = new Set([
      ...fingerprint.members.filter((member) => !knownMembers.has(member)).map(entryName),
      ...known.members.filter((member) => !actualMembers.has(member)).map(entryName),
    ]);
    if (changed.size) lines.push(`  changed members: ${[...changed].join(", ")}`);
    problems.push(lines.join("\n"));
  }
  return problems;
}

async function main() {
  const [command = "check", bundlePath] = process.argv.slice(2);
  if (!["check", "update"].includes(command)) throw new Error("usage: player.mts check|update [bundle.js]");
  const bundle = bundlePath
    ? { name: bundlePath.split("/").pop() ?? bundlePath, source: await readFile(bundlePath, "utf8") }
    : await fetchBundle();
  const actual = extract(bundle.source);
  if (command === "update") {
    console.log(`bundle: ${bundle.name}`);
    const fingerprints = Object.fromEntries(
      Object.entries(actual.fingerprints).map(([label, { hash, units, members }]) => [label, { hash, units, members }]),
    );
    const recorded: Recorded = { bundle: bundle.name, constants: actual.constants, fingerprints };
    await writeFile(EXPECTED_PATH, `${JSON.stringify(recorded, null, 2)}\n`);
    return;
  }
  const expected: Recorded = JSON.parse(await readFile(EXPECTED_PATH, "utf8"));
  console.log(`bundle: ${bundle.name} (recorded: ${expected.bundle})`);
  // Public CI logs must not contain the code of the official player.
  const problems = compare(expected, actual, !process.env.CI);
  for (const problem of problems) console.log(`\n${problem}`);
  if (problems.length) process.exitCode = 1;
  else console.log("no changes");
}

await main();
