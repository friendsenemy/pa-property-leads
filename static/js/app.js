/* PA Property Leads (Greene County) — one-file app: gate, boards, detail card, shared notes, My Leads. */
const C = window.PAPL;
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => s == null ? "" : String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => n == null || n === "" ? "" : "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const num = (n) => n == null ? "" : Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
const ac = (n) => !n ? "" : Number(n).toLocaleString("en-US", { maximumFractionDigits: n < 10 ? 2 : 0 });
const HARD = new Set(["estate_notice", "sheriff", "judicial", "obit", "owner_estate", "upset", "unsound", "major_repair"]);
const GASK = new Set(["gas_near", "pad_on_parcel", "new_permit_near", "deed_unleased", "deed_leased_not_producing", "deed_unknown"]);
const STATUS = { "": "—", hot: "Hot", pursuing: "Pursuing", followup: "Follow up", contacted: "Contacted", dead: "Dead / pass" };

/* ---------- passcode gate (same code as the Maryland tool) ---------- */
async function sha(t) { const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(t)); return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join(""); }
function gate() {
    return new Promise((ok) => {
        try { if (localStorage.getItem("papl_gate") === C.GATE_SHA256) return ok(); } catch {}
        const g = document.createElement("div"); g.id = "gate";
        g.innerHTML = `<form><h2 style="color:var(--cyan)">PA Property Leads</h2><div class="dim small">Greene County · enter the team passcode</div><input type="password" id="gp" autocomplete="current-password" autofocus><button class="btn pri" style="width:100%">Enter</button><div id="ge" class="small" style="color:var(--red);margin-top:8px"></div></form>`;
        document.body.appendChild(g);
        g.querySelector("form").onsubmit = async (e) => {
            e.preventDefault();
            const h = await sha(g.querySelector("#gp").value.trim());
            if (h === C.GATE_SHA256) { try { localStorage.setItem("papl_gate", h); } catch {} g.remove(); ok(); }
            else g.querySelector("#ge").textContent = "Wrong passcode";
        };
    });
}

/* ---------- shared notes (same Google Sheet as MD; ids prefixed "PA:") ---------- */
const Notes = {
    latest: {}, history: {}, error: null, sig: "",
    nid: (id) => "PA:" + id,
    author() { try { return localStorage.getItem("mdpl_author") || ""; } catch { return ""; } },
    setAuthor(v) { try { localStorage.setItem("mdpl_author", (v || "").trim()); } catch {} },
    async load(quiet) {
        try {
            const r = await fetch(`${C.SHARED_NOTES_URL}?t=${Date.now()}`, { cache: "no-store" });
            const rows = ((await r.json()).rows || []).filter((x) => String(x.id || "").startsWith("PA:"))
                .sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
            const sig = rows.length + "|" + (rows[0] ? rows[0].ts : "");
            if (quiet && sig === this.sig) return false;
            this.sig = sig; this.latest = {}; this.history = {};
            for (const x of rows) { (this.history[x.id] = this.history[x.id] || []).push(x); if (!this.latest[x.id]) this.latest[x.id] = x; }
            this.error = null;
        } catch (e) { this.error = String(e); }
        App.refreshBadges();
        return true;
    },
    get(id) { return this.latest[this.nid(id)] || null; },
    async save(id, status, notes, label) {
        const row = { ts: new Date().toISOString(), author: this.author() || "unknown", tab: "pa-" + App.tab, id: this.nid(id), label: label || "", status, notes };
        this.latest[row.id] = row; (this.history[row.id] = this.history[row.id] || []).unshift(row);
        try {
            const r = await fetch(C.SHARED_NOTES_URL, { method: "POST", body: JSON.stringify(row) });
            const j = await r.json().catch(() => ({}));
            if (j && j.ok === false) throw new Error(j.error || "rejected");
            this.error = null; return true;
        } catch (e) { this.error = String(e); return false; }
    },
    card(r) {
        const link = (h) => h.replace(/(\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}-\d{3}-\d{4}\b)/g, (p) => `<a href="tel:${p.replace(/\D/g, "")}">${p}</a>`);
        return `<div class="note"><div class="h">${esc(new Date(r.ts).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }))} · ${esc(r.author)}${r.status ? ` · <span class="badge ${esc(r.status)}">${esc(STATUS[r.status] || r.status)}</span>` : ""}</div>${link(esc(r.notes || ""))}</div>`;
    },
};

/* ---------- app ---------- */
const App = {
    tab: "leads", board: null, lookup: [], q: "", filt: {}, sort: { minerals: { k: "acres", d: -1 } },
    TABS: [
        ["leads", "Stacked Leads"], ["minerals", "Oil & Gas"], ["estates", "Estates"], ["sheriff", "Sheriff Sales"],
        ["tax", "Tax Sales"], ["lookup", "Parcel Lookup"], ["mine", "My Leads"], ["guide", "How to use"],
    ],
    async init() {
        await gate();
        $("#app").innerHTML = `<div class="explain">Loading Greene County data…</div>`;
        const [b, l] = await Promise.all([fetch("data/board.json", { cache: "no-store" }).then((r) => r.json()), fetch("data/lookup.json").then((r) => r.json())]);
        this.lookup = l;
        this.byId = {}; for (const x of b.rows) this.byId[x.id] = x;
        b.leads = b.leads.map((i) => this.byId[i]); b.minerals = b.minerals.map((i) => this.byId[i]);
        this.board = b;
        $("#gen").textContent = "Updated " + new Date(b.generated).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
        const t = (location.hash || "").replace("#", ""); if (this.TABS.some(([k]) => k === t)) this.tab = t;
        this.render();
        Notes.load();
        setInterval(() => { if (document.visibilityState === "visible") Notes.load(true); }, 120000);
        window.addEventListener("focus", () => Notes.load(true));
    },
    refreshBadges() { if (this.board) this.renderTabs(); if (["mine"].includes(this.tab)) this.renderBody(); },
    renderTabs() {
        const n = { leads: this.board.leads.length, minerals: this.board.minerals.length, estates: this.board.estates.length,
            sheriff: this.board.sheriff.filter((s) => s.sale_date >= today()).length, tax: this.taxRows().length,
            mine: Object.values(Notes.latest).filter((r) => r.status && r.status !== "dead").length };
        $("#tabs").innerHTML = this.TABS.map(([k, l]) => `<button class="tab ${k === this.tab ? "on" : ""}" data-t="${k}">${l}${n[k] != null ? `<span class="n">${n[k]}</span>` : ""}</button>`).join("");
        $("#tabs").querySelectorAll(".tab").forEach((b) => b.onclick = () => { this.tab = b.dataset.t; location.hash = this.tab; this.q = ""; this.render(); });
    },
    render() { this.renderTabs(); this.renderBody(); },
    renderBody() { const f = this["tab_" + this.tab]; $("#app").innerHTML = f.call(this); this.wire(); },
    wire() {
        $("#app").querySelectorAll("tbody tr[data-id]").forEach((tr) => tr.onclick = () => this.open(tr.dataset.id));
        const q = $("#q"); if (q) { q.value = this.q; q.oninput = () => { this.q = q.value; clearTimeout(this._t); this._t = setTimeout(() => { const pos = q.selectionStart; this.renderBody(); const nq = $("#q"); nq.focus(); nq.setSelectionRange(pos, pos); }, 250); }; }
        $("#app").querySelectorAll("select[data-f], input[data-f]").forEach((s) => { s.value = this.filt[this.tab + s.dataset.f] ?? s.value; s.onchange = () => { this.filt[this.tab + s.dataset.f] = s.type === "checkbox" ? s.checked : s.value; this.renderBody(); }; if (s.type === "checkbox") s.checked = !!this.filt[this.tab + s.dataset.f]; });
        $("#app").querySelectorAll("th[data-s]").forEach((th) => th.onclick = () => { const k = th.dataset.s; const cur = this.sort[this.tab]; this.sort[this.tab] = { k, d: cur && cur.k === k ? -cur.d : -1 }; this.renderBody(); });
        const csv = $("#csv"); if (csv) csv.onclick = () => this.csv();
    },
    f(k) { return this.filt[this.tab + k]; },
    /* Every word typed must appear somewhere, in any order, ignoring periods/commas:
       "Robert M. Smith" finds "SMITH ROBERT M ET AL", "mcdonald" finds "MC DONALD". */
    hit(q, vals) {
        const words = String(q || "").toLowerCase().replace(/[.,;:'"]/g, " ").split(/\s+/).filter(Boolean);
        if (!words.length) return true;
        const hay = vals.filter(Boolean).join(" ").toLowerCase().replace(/[.,;:'"]/g, " ");
        const tight = hay.replace(/\s+/g, "");
        const esc = (w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        return words.every((w) => new RegExp("(^|[\\s/(-])" + esc(w)).test(hay) || (w.length >= 4 && tight.includes(w)));
    },
    match(x) {
        if (!this.q) return true;
        return this.hit(this.q, [x.id, x.ctrl, x.owner, x.owner2, x.mail, x.city, x.address, x.defendant, x.name, x.late_of, x.estate_name]);
    },
    sorted(rows, getters) {
        const s = this.sort[this.tab]; if (!s || !getters[s.k]) return rows;
        const g = getters[s.k];
        return rows.slice().sort((a, b) => { const x = g(a), y = g(b); return (x > y ? 1 : x < y ? -1 : 0) * s.d; });
    },
    chips(sig) {
        return Object.keys(sig || {}).map((k) => `<span class="chip ${HARD.has(k) ? "hard" : GASK.has(k) ? "gas" : "soft"}" title="${esc(sig[k])}">${esc(this.board.labels[k] || k)}</span>`).join("");
    },
    status(id) { const n = Notes.get(id); return n && n.status ? `<span class="badge ${esc(n.status)}">${esc(STATUS[n.status] || n.status)}</span>` : ""; },
    head(cols) { return `<thead><tr>${cols.map(([l, k, cls]) => `<th ${k ? `data-s="${k}"` : ""} class="${cls || ""}">${l}</th>`).join("")}</tr></thead>`; },
    filters(extra) { return `<div class="filters"><input id="q" placeholder="Name (any order), parcel ID or town…" style="min-width:240px">${extra || ""}<span class="spacer"></span><button class="btn" id="csv">Download CSV</button></div>`; },

    /* ---- Stacked leads ---- */
    tab_leads() {
        let rows = this.board.leads.filter((x) => this.match(x));
        const mh = +(this.f("mh") || 0); if (mh) rows = rows.filter((x) => x.hard >= mh);
        if (this.f("gas")) rows = rows.filter((x) => x.gas);
        const sg = this.f("sg"); if (sg) rows = rows.filter((x) => x.signals[sg]);
        rows = this.sorted(rows, { score: (x) => x.score, hard: (x) => x.hard, acres: (x) => x.acres || 0, owner: (x) => x.owner || "", gas: (x) => (x.gas || {}).producing_near || 0 });
        this.cur = rows;
        const stacked = this.board.leads.filter((x) => x.hard >= 2).length;
        const sigOpts = Object.keys(this.board.points).map((k) => `<option value="${k}">${esc(this.board.labels[k] || k)}</option>`).join("");
        return `<div class="stats">
            <div class="stat cyan"><div class="v">${this.board.leads.length}</div><div class="l">Mineral parcels with a reason to sell</div></div>
            <div class="stat red"><div class="v">${stacked}</div><div class="l">Stacked (2+ hard signals)</div></div>
            <div class="stat gas"><div class="v">${this.board.leads.filter((x) => x.gas).length}</div><div class="l">Leads that also sit in the gas field</div></div>
            <div class="stat purple"><div class="v">${this.board.sheriff.filter((s) => s.sale_date >= today()).length}</div><div class="l">Upcoming sheriff sales</div></div></div>
            <div class="explain"><b>Only parcels that could pay royalty checks are shown:</b> inside the gas field (producing wells within ¾ mile, a pad on the parcel, or new permits within 1.5 miles), ${this.board.min_acres || 2}+ acres, not owned by a gas/coal company, and not already sold off per the deed checks. <b>Stacked Leads</b> ranks them by how many reasons the owner may want to sell. <b>Red chips</b> are hard signals (estate notice, tax sale list, sheriff sale, owner is an estate, unsound house). <b>Orange chips</b> mean producing gas wells or a new permit nearby — the owner may also hold mineral rights or royalties worth buying. Click any row for the full card.</div>
            ${this.filters(`<select data-f="mh"><option value="0">Any hard signals</option><option value="1">1+ hard</option><option value="2">2+ hard (stacked)</option></select>
              <select data-f="sg"><option value="">Any signal</option>${sigOpts}</select><label class="small dim"><input type="checkbox" data-f="gas"> In the gas field</label>`)}
            <div class="tablewrap"><table>${this.head([["Score", "score"], ["Hard", "hard"], ["Owner", "owner"], ["Parcel ID"], ["Signals"], ["Acres", "acres", "hide-sm"], ["Wells ≤¾ mi", "gas", "hide-sm"], ["Status"]])}
            <tbody>${rows.slice(0, 500).map((x) => `<tr data-id="${esc(x.id)}"><td class="score">${x.score}</td><td class="mono">${x.hard}</td>
              <td><b>${esc(x.owner || "")}</b>${x.owner2 ? `<div class="dim small">${esc(x.owner2)}</div>` : ""}<div class="dim small">${esc([x.city, x.st].filter(Boolean).join(", "))}</div></td>
              <td class="mono small">${esc(x.id)}</td><td>${this.chips(x.signals)}</td><td class="mono hide-sm">${ac(x.acres)}</td>
              <td class="mono hide-sm">${x.gas ? x.gas.producing_near : ""}</td><td>${this.status(x.id)}</td></tr>`).join("")}</tbody></table></div>
            ${rows.length > 500 ? `<div class="dim small" style="margin-top:6px">Showing 500 of ${rows.length}. Narrow with search or filters, or download the CSV.</div>` : ""}`;
    },

    /* ---- Minerals ---- */
    tab_minerals() {
        let rows = this.board.minerals.filter((x) => this.match(x));
        if (this.f("prod")) rows = rows.filter((x) => x.gas.producing_near > 0);
        if (this.f("mot")) rows = rows.filter((x) => Object.keys(x.signals).some((k) => HARD.has(k) || ["out_of_state", "out_of_county", "old_deed", "life_estate"].includes(k)));
        const ma = +(this.f("ma") || 0); if (ma) rows = rows.filter((x) => (x.acres || 0) >= ma);
        rows = this.sorted(rows, { acres: (x) => x.acres || 0, prod: (x) => x.gas.producing_near, vol: (x) => x.gas.gas_12mo_near, score: (x) => x.score, owner: (x) => x.owner || "" });
        this.cur = rows;
        const per = this.board.periods || [];
        return `<div class="stats">
            <div class="stat gas"><div class="v">${this.board.counts.minerals}</div><div class="l">Parcels in the gas field worth a look</div></div>
            <div class="stat cyan"><div class="v">${this.board.minerals.filter((x) => x.gas.producing_near > 0).length}</div><div class="l">With producing wells within ¾ mile</div></div>
            <div class="stat purple"><div class="v">${this.board.minerals.filter((x) => x.gas.on_parcel > 0).length}</div><div class="l">With a well pad on the parcel</div></div>
            <div class="stat"><div class="v small">${esc(per.length ? per[per.length - 1] + " – " + per[0] : "")}</div><div class="l">Production months counted</div></div></div>
            <div class="explain"><b>Oil &amp; Gas</b> finds parcels sitting inside Marcellus drilling units. If the surface owner also owns the gas, they are probably getting (or about to get) <b>royalty checks</b> — and mineral buyers pay cash for those checks, often 4–8 years of income up front. Best targets: <b>absentee owners</b>, <b>estates and heirs</b> (split interests nobody manages), and <b>big acreage</b> next to new permits. Always confirm the owner still holds the minerals (deed search at the Recorder) — many Greene tracts had the coal or gas severed decades ago.</div>
            ${this.filters(`<label class="small dim"><input type="checkbox" data-f="prod"> Producing wells nearby</label><label class="small dim"><input type="checkbox" data-f="mot"> Has a motivation signal</label>
              <select data-f="ma"><option value="0">Any acreage</option><option value="10">10+ acres</option><option value="50">50+ acres</option><option value="100">100+ acres</option></select>`)}
            <div class="tablewrap"><table>${this.head([["Owner", "owner"], ["Parcel ID"], ["Acres", "acres"], ["Producing ≤¾ mi", "prod"], ["Their 12-mo gas (Mcf)", "vol", "hide-sm"], ["Operators", "", "hide-sm"], ["Signals"], ["Status"]])}
            <tbody>${rows.slice(0, 500).map((x) => `<tr data-id="${esc(x.id)}"><td><b>${esc(x.owner || "")}</b><div class="dim small">${esc([x.city, x.st].filter(Boolean).join(", "))}</div></td>
              <td class="mono small">${esc(x.id)}</td><td class="mono">${ac(x.acres)}</td><td class="mono">${x.gas.producing_near}${x.gas.on_parcel ? ` <span class="chip gas">pad on parcel</span>` : ""}</td>
              <td class="mono hide-sm">${num(x.gas.gas_12mo_near)}</td><td class="small hide-sm">${esc((x.gas.operators || []).join(", "))}</td><td>${this.chips(x.signals)}</td><td>${this.status(x.id)}</td></tr>`).join("")}</tbody></table></div>`;
    },

    /* ---- Estates ---- */
    tab_estates() {
        let rows = this.board.estates.filter((x) => this.match(x));
        this.cur = rows;
        const owned = (e) => this.board.leads.filter((x) => x.estate_name === e.name);
        return `<div class="explain"><b>Estate notices</b> from The Greene Reports (the county legal journal). An estate notice means someone died and a personal representative is settling things — often heirs who live elsewhere and want to sell the house <b>and</b> any mineral interests. Rows marked <b>owns land</b> matched a current parcel owner by name; verify before calling. Contact the representative (executor) or the estate attorney listed.</div>
            ${this.filters()}
            <div class="tablewrap"><table>${this.head([["Published"], ["Decedent"], ["Late of"], ["Representative(s)"], ["Attorney", "", "hide-sm"], ["Parcels"]])}
            <tbody>${rows.map((e) => { const o = owned(e); return `<tr ${o.length ? `data-id="${esc(o[0].id)}"` : ""}><td class="mono small">${esc(e.first_pub || "")}</td><td><b>${esc(e.name)}</b></td><td class="small">${esc(e.late_of || "")}</td>
              <td class="small">${(e.reps || []).map((r) => `${esc(r.role)}: ${esc(r.text)}`).join("<br>")}</td><td class="small hide-sm">${esc(e.attorney || "")}</td>
              <td>${o.length ? `<span class="chip hard">owns land · ${o.length}</span>` : `<span class="dim small">no match</span>`}</td></tr>`; }).join("")}</tbody></table></div>`;
    },

    /* ---- Sheriff ---- */
    tab_sheriff() {
        let rows = this.board.sheriff.filter((x) => this.match(x));
        if (!this.f("past")) rows = rows.filter((s) => s.sale_date >= today() || /postpon/i.test(s.status || ""));
        rows.sort((a, b) => a.sale_date.localeCompare(b.sale_date));
        this.cur = rows;
        return `<div class="explain">Only sheriff sales on mineral parcels (gas field, 2+ acres) are listed — most Greene sheriff sales are small town lots, so this list is often empty. <b>Sheriff sales</b> are mortgage and judgment foreclosures auctioned at the Greene County Courthouse. Before the sale the owner can still sell — reach them early. Many get postponed or settled. The <b>handbill</b> link has the legal description.</div>
            ${this.filters(`<label class="small dim"><input type="checkbox" data-f="past"> Show past sales</label>`)}
            <div class="tablewrap"><table>${this.head([["Sale date"], ["Defendant (owner)"], ["Plaintiff"], ["Property"], ["Judgment"], ["Status"], ["Parcel"]])}
            <tbody>${rows.map((s) => `<tr ${s.id ? `data-id="${esc(this.byId[s.id] ? s.id : "SHERIFF:" + s.case)}"` : `data-id="SHERIFF:${esc(s.case)}"`}><td class="mono">${esc(s.sale_date)}</td><td><b>${esc(s.defendant)}</b>${s.estate ? ` <span class="chip hard">estate</span>` : ""}</td>
              <td class="small">${esc(s.plaintiff)}</td><td class="small">${esc(s.address)}</td><td class="mono">${money(s.judgment)}</td><td class="small">${esc(s.status)}</td>
              <td class="mono small">${esc(s.id || "")}${s.handbill ? ` · <a href="${esc(s.handbill)}" target="_blank" onclick="event.stopPropagation()">handbill</a>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
    },

    /* ---- Tax sales ---- */
    taxRows() { return [...this.board.leads].filter((x) => x.tax); },
    tab_tax() {
        let rows = this.taxRows().filter((x) => this.match(x));
        const l = this.f("list"); if (l) rows = rows.filter((x) => x.tax.list === l);
        if (this.f("coal")) rows = rows.filter((x) => x.coal_account || (x.tax.id || "") === "00-00-000");
        rows = this.sorted(rows, { amt: (x) => x.tax.amount || 0, owner: (x) => x.owner || "", score: (x) => x.score });
        this.cur = rows;
        const links = this.board.tax_lists || {};
        return `<div class="explain"><b>Tax Claim Bureau lists.</b> <b>Upset sale</b> (held in September; the 2026 sale was <b>Sept 16, 2026</b>) = taxes 2+ years delinquent; sold subject to mortgages and liens. Parcels on this list that did not sell or pay are now headed to the next <b>Judicial sale</b> (free and clear of liens; the 2026 one was June 3, 2026), so those owners are still delinquent and running out of time. Call the Tax Claim Bureau (724-852-5232) to check whether a parcel is still unpaid. Rows with map <b>00-00-000</b> are separately assessed coal/mineral accounts.
            ${Object.entries(links).map(([k, u]) => ` <a href="${esc(u)}" target="_blank">${esc(k)} list PDF</a>`).join(" ·")}</div>
            ${this.filters(`<select data-f="list"><option value="">Both lists</option><option value="upset">Upset</option><option value="judicial">Judicial</option></select><label class="small dim"><input type="checkbox" data-f="coal"> Mineral/coal accounts only</label>`)}
            <div class="tablewrap"><table>${this.head([["List"], ["Owner", "owner"], ["Parcel ID"], ["Amount / detail", "amt"], ["Other signals"], ["Score", "score"]])}
            <tbody>${rows.map((x) => `<tr data-id="${esc(x.id)}"><td><span class="chip hard">${esc(x.tax.list)}</span></td><td><b>${esc(x.owner || x.tax.owner_desc || "")}</b><div class="dim small">${esc(x.tax.muni || "")}</div></td>
              <td class="mono small">${esc(x.tax.id || x.id)}<div class="dim">ctrl ${esc(x.tax.ctrl)}</div></td><td class="mono">${x.tax.amount ? money(x.tax.amount) : esc(x.tax.acres ? x.tax.acres + " ac" : "")}</td>
              <td>${this.chips(Object.fromEntries(Object.entries(x.signals).filter(([k]) => !["upset", "judicial"].includes(k))))}</td><td class="score">${x.score}</td></tr>`).join("")}</tbody></table></div>`;
    },

    /* ---- Lookup ---- */
    tab_lookup() {
        const q = this.q.trim().toLowerCase();
        let rows = q.length < 2 ? [] : this.lookup.filter((r) => this.hit(q, [r[0], r[1], r[3], r[4], r[5], r[6]])).slice(0, 300);
        this.cur = rows.map((r) => ({ id: r[0], ctrl: r[1], owner: r[3], owner2: r[4], mail: r[5], city: r[6], st: r[7], lu: r[8], blight: r[9], acres: r[10], deed: r[11] }));
        return `<div class="explain"><b>Parcel Lookup</b> searches all ${num(this.lookup.length)} Greene County parcels by owner, parcel ID (e.g. 06-05-124), control number or mailing address. Type at least 2 characters.</div>
            ${this.filters()}
            <div class="tablewrap"><table>${this.head([["Parcel ID"], ["Owner"], ["Mailing"], ["Use"], ["Condition"], ["Acres"], ["Deed"], ["Lead?"]])}
            <tbody>${rows.map((r) => `<tr data-id="${esc(r[0])}"><td class="mono small">${esc(r[0])}<div class="dim">${esc(r[1])}</div></td><td><b>${esc(r[3])}</b><div class="dim small">${esc(r[4])}</div></td>
              <td class="small">${esc(r[5])}<div class="dim">${esc(r[6])} ${esc(r[7])}</div></td><td class="small">${esc(r[8])}</td><td class="small">${esc(r[9])}</td><td class="mono">${ac(r[10])}</td>
              <td class="mono small">${esc(r[11])}</td><td>${this.byId[r[0]] ? `<span class="score">${this.byId[r[0]].score}</span>` : ""}</td></tr>`).join("")}</tbody></table></div>`;
    },

    /* ---- My Leads ---- */
    tab_mine() {
        const rows = Object.values(Notes.latest).filter((r) => r.status && r.status !== "dead" && this.hit(this.q, [r.label, r.id, r.notes]));
        this.cur = rows;
        return `<div class="explain"><b>My Leads</b> are the Greene County leads you or Todd marked with a status. Notes are shared through the same sheet as the Maryland tool, so everyone with the passcode sees them. ${Notes.error ? `<span style="color:var(--red)">Could not reach the shared sheet right now.</span>` : ""}</div>
            ${this.filters()}
            <div class="tablewrap"><table>${this.head([["Status"], ["Lead"], ["Parcel ID"], ["Latest note"], ["By"], ["When"]])}
            <tbody>${rows.map((r) => { const id = r.id.slice(3); return `<tr data-id="${esc(id)}"><td><span class="badge ${esc(r.status)}">${esc(STATUS[r.status] || r.status)}</span></td><td><b>${esc(r.label)}</b></td>
              <td class="mono small">${esc(id)}</td><td class="small">${esc((r.notes || "").slice(0, 160))}</td><td class="small">${esc(r.author)}</td><td class="small mono">${esc(String(r.ts).slice(0, 10))}</td></tr>`; }).join("") || `<tr><td colspan="6" class="dim">Nothing yet — open any lead and set a status.</td></tr>`}</tbody></table></div>`;
    },

    tab_guide() {
        return `<div class="explain" style="font-size:.95rem;line-height:1.6">
        <h3 style="color:var(--cyan)">How the money works in Greene County</h3>
        <p>Greene sits on the Marcellus Shale. Operators (EQT, CNX, Range, Coterra and others) lease the gas from whoever owns it and pay a royalty — Pennsylvania law guarantees at least <b>12.5%</b> of production value. That's the monthly check your dad gets. Those checks are an asset anyone can buy: mineral buyers pay a lump sum today for the future checks.</p>
        <h3 style="color:var(--cyan)">Three ways to make money from this tool</h3>
        <p><b>1. Buy the house/land from a motivated owner</b> (estate, tax sale, sheriff sale, out-of-state heir). If the minerals come with the land, you get the royalties too — or keep the surface and sell the minerals separately.<br>
        <b>2. Buy royalty or mineral interests directly.</b> Absentee owners and heirs split 4 ways often prefer cash now. Typical offers run a multiple of 3–6 years of recent royalty income. Verify the income with their check stubs and the operator's division order.<br>
        <b>3. Wholesale / refer</b> mineral leads to established buyers for a finder's fee once you have a signed letter of intent.</p>
        <h3 style="color:var(--cyan)">Before you make an offer</h3>
        <p>• Confirm who owns the minerals — many Greene tracts had coal or gas <b>severed</b> long ago. Search the deed chain at the Greene County Recorder of Deeds (in person in Waynesburg or their online SearchIQS). Look for "excepting and reserving" language.<br>
        • Look up the wells in the <a href="https://greenport.pa.gov/ReportExtracts/OG/OilGasWellProdReport" target="_blank">DEP production report</a> and the <a href="https://gis.dep.pa.gov/PaOilAndGasMapping/" target="_blank">PA Oil &amp; Gas map</a> to see which unit the parcel is in.<br>
        • Ask for the owner's last 12 royalty statements — the decimal interest on them is what you are buying.<br>
        • Use a Pennsylvania oil &amp; gas attorney for the deed/assignment. I'm not a lawyer, and these numbers are a starting point, not an appraisal.</p>
        <h3 style="color:var(--cyan)">Points</h3><p>${Object.entries(this.board.points).map(([k, v]) => `${esc(this.board.labels[k] || k)} <b>${v}</b>`).join(" · ")}</p></div>`;
    },

    /* ---- detail card ---- */
    find(id) {
        if (this.byId[id]) return this.byId[id];
        if (id.startsWith("SHERIFF:")) { const s = this.board.sheriff.find((x) => "SHERIFF:" + x.case === id); if (s) return { id, owner: s.defendant, signals: { sheriff: `${s.sale_date} · ${s.plaintiff} · ${money(s.judgment)} · ${s.status}` }, sheriff: s, score: 35, hard: 1 }; }
        const r = this.lookup.find((x) => x[0] === id);
        if (r) return { id: r[0], ctrl: r[1], pid: r[2], owner: r[3], owner2: r[4], mail: r[5], city: r[6], st: r[7], lu: r[8], blight: r[9], acres: r[10], deed: r[11], lat: r[12], lon: r[13], signals: {}, score: 0, hard: 0 };
        return { id, owner: "", signals: {}, score: 0, hard: 0 };
    },
    async details() {
        if (!this._det) this._det = fetch("data/details.json").then((r) => r.json()).catch(() => ({}));
        return this._det;
    },
    async open(id) {
        const x = this.find(id); this.openId = id;
        const d = (await this.details())[id] || {};
        const g = x.gas ? { ...x.gas, nearest: d.nearest || [], new_permits: d.new_permits || [] } : null;
        const s = x.sheriff || d.sheriff, t = d.tax || x.tax, e = d.estate, coal = d.coal;
        const vision = x.pid ? `<a href="${C.VISION}${x.pid}" target="_blank">County assessment card (Vision)</a>` : "";
        const map = x.lat ? `<a href="https://www.google.com/maps?q=${x.lat},${x.lon}" target="_blank">Google Maps</a> · <a href="https://gis.dep.pa.gov/PaOilAndGasMapping/" target="_blank">PA Oil &amp; Gas map</a>` : "";
        const hist = (Notes.history[Notes.nid(id)] || []).slice(0, 12).map((r) => Notes.card(r)).join("");
        const cur = Notes.get(id) || {};
        $("#modal").innerHTML = `<button class="x" onclick="App.close()">×</button>
          <h2>${esc(x.owner || "Unknown owner")}</h2><div class="dim">${esc(x.owner2 || "")}</div>
          <div style="margin:8px 0">${x.score ? `<span class="score">Score ${x.score}</span> · ${x.hard} hard · ` : ""}${this.chips(x.signals)}</div>
          <div class="kv">
            <div class="k">Parcel ID</div><div class="mono">${esc(x.id)}${x.ctrl ? ` · control ${esc(x.ctrl)}` : ""}</div>
            <div class="k">Mailing address</div><div>${esc([x.mail, x.city, x.st, x.zip].filter(Boolean).join(", "))}</div>
            <div class="k">Land use / condition</div><div>${esc(x.lu || "")} · ${esc(x.blight || "")}</div>
            <div class="k">Acres</div><div>${ac(x.acres)}</div>
            <div class="k">Deed</div><div class="mono">${esc(x.deed || "")}</div>
            <div class="k">Links</div><div>${[vision, map].filter(Boolean).join(" · ")}</div>
          </div>
          <h3>Why it's a lead</h3>${Object.entries(x.signals || {}).map(([k, v]) => `<div class="small"><span class="chip ${HARD.has(k) ? "hard" : GASK.has(k) ? "gas" : "soft"}">${esc(this.board.labels[k] || k)}</span> ${esc(v)}</div>`).join("") || `<div class="dim small">No signals — plain parcel record.</div>`}
          ${e ? `<h3>Estate notice</h3><div class="kv"><div class="k">Decedent</div><div>${esc(e.name)} · late of ${esc(e.late_of || "")}</div><div class="k">Published</div><div>${esc(e.first_pub || "")}</div>${(e.reps || []).map((r) => `<div class="k">${esc(r.role)}</div><div>${esc(r.text)}</div>`).join("")}<div class="k">Attorney</div><div>${esc(e.attorney || "")}</div></div><div class="dim small">Matched by name — confirm the decedent is this owner before reaching out.</div>` : ""}
          ${s ? `<h3>Sheriff sale</h3><div class="kv"><div class="k">Sale date</div><div>${esc(s.sale_date)} · ${esc(s.status)}</div><div class="k">Case</div><div class="mono">${esc(s.case)}</div><div class="k">Plaintiff</div><div>${esc(s.plaintiff)}</div><div class="k">Attorney</div><div>${esc(s.attorney || "")}</div><div class="k">Judgment</div><div>${money(s.judgment)}</div><div class="k">Address</div><div>${esc(s.address)}</div></div>` : ""}
          ${t ? `<h3>Tax claim</h3><div class="kv"><div class="k">List</div><div>${esc(t.list)} ${esc(t.year || "")}</div><div class="k">Control #</div><div class="mono">${esc(t.ctrl)}</div><div class="k">Amount</div><div>${t.amount ? money(t.amount) : ""}</div>${t.exposed ? `<div class="k">Years exposed</div><div>${esc(t.exposed)}</div>` : ""}<div class="k">Listing text</div><div class="small mono">${esc(t.raw || "")}</div></div>` : ""}
          ${g ? `<h3>Gas wells around this parcel</h3><div class="kv"><div class="k">Producing within ¾ mi</div><div>${g.producing_near} (of ${g.wells_near} wells)</div><div class="k">Wells on the parcel</div><div>${g.on_parcel}</div><div class="k">12-month gas from those wells</div><div>${num(g.gas_12mo_near)} Mcf</div><div class="k">Operators</div><div>${esc((g.operators || []).join(", "))}</div></div>
            ${g.nearest.length ? `<div class="tablewrap" style="margin-top:8px"><table><thead><tr><th>Well</th><th>Operator</th><th>Distance</th><th>12-mo Mcf</th><th>Last month</th><th>Spud</th></tr></thead><tbody>${g.nearest.map((w) => `<tr><td class="small">${esc(w.name)}<div class="dim mono">${esc(w.api)}</div></td><td class="small">${esc(w.op)}</td><td class="mono">${w.mi} mi</td><td class="mono">${num(w.gas_12mo)}</td><td class="mono">${num(w.last)}</td><td class="mono small">${esc(w.spud || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${g.new_permits.length ? `<div class="small" style="margin-top:6px"><b>New permits nearby:</b> ${g.new_permits.map((p) => `${esc(p.farm)} (${esc(p.op)}, ${esc(String(p.issued).slice(0, 10))})`).join("; ")}</div>` : ""}
            <div class="dim small" style="margin-top:6px">Rough royalty math: a 1% net royalty interest in a unit producing 1,000,000 Mcf/yr at $2.50/Mcf ≈ $25,000/yr. The owner's statements show their real decimal.</div>` : ""}
          ${coal ? `<h3>Coal</h3><div class="small">${Object.entries(coal).map(([k, v]) => `<span class="chip">${esc(k.replace("_", " "))}</span> ${esc(Object.values(v || {}).filter(Boolean).slice(0, 3).join(" · "))}`).join("<br>")}</div><div class="dim small">Coal under this parcel is mined out or being mined — coal rights were often severed and sold decades ago. Gas rights may still be with the surface owner; check the deed.</div>` : ""}
          <h3>Notes &amp; status (shared)</h3>
          <div class="filters"><input id="nAuthor" placeholder="Your name" value="${esc(Notes.author())}" style="width:140px">
            <select id="nStatus">${Object.entries(STATUS).map(([k, l]) => `<option value="${k}" ${cur.status === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
          <textarea id="nText" rows="4" style="width:100%" placeholder="Called, left voicemail… Heirs: … Next: …"></textarea>
          <div class="filters" style="margin-top:6px"><button class="btn pri" id="nSave">Save note</button><span id="nMsg" class="small dim"></span></div>
          <div id="nHist">${hist}</div>`;
        $("#overlay").classList.add("on");
        $("#nAuthor").onchange = (ev) => Notes.setAuthor(ev.target.value);
        $("#nSave").onclick = async () => {
            Notes.setAuthor($("#nAuthor").value);
            const ok = await Notes.save(id, $("#nStatus").value, $("#nText").value.trim(), `${x.owner || ""} · ${id}`);
            $("#nMsg").textContent = ok ? "Saved for everyone" : "Saved here only — could not reach the shared sheet";
            $("#nText").value = ""; $("#nHist").innerHTML = (Notes.history[Notes.nid(id)] || []).slice(0, 12).map((r) => Notes.card(r)).join("");
            this.renderTabs();
        };
        Notes.load(true).then((changed) => { if (changed && this.openId === id && $("#nHist")) $("#nHist").innerHTML = (Notes.history[Notes.nid(id)] || []).slice(0, 12).map((r) => Notes.card(r)).join(""); });
    },
    close() { $("#overlay").classList.remove("on"); this.openId = null; this.renderBody(); },

    csv() {
        const rows = this.cur || [];
        const cols = ["id", "ctrl", "owner", "owner2", "mail", "city", "st", "zip", "acres", "deed", "score", "hard"];
        const out = [cols.concat(["signals", "producing_wells_near"]).join(",")].concat(rows.map((x) => cols.map((c) => JSON.stringify(x[c] ?? "")).concat([JSON.stringify(Object.keys(x.signals || {}).join("; ")), (x.gas || {}).producing_near || ""]).join(",")));
        const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([out.join("\n")], { type: "text/csv" })); a.download = `greene-${this.tab}.csv`; a.click();
    },
};
function today() { return new Date().toISOString().slice(0, 10); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#overlay").classList.contains("on")) App.close(); });
document.addEventListener("DOMContentLoaded", () => {
    $("#overlay").onclick = (e) => { if (e.target.id === "overlay") App.close(); };
    App.init().catch((e) => { $("#app").innerHTML = `<div class="explain" style="color:var(--red)">Could not load data: ${esc(e)}</div>`; });
});
