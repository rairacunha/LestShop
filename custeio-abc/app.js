/* Custeio ABC do escritório — motor de cálculo e interface (sem backend). */
(function () {
  "use strict";

  const CFG = window.CUSTEIO;
  const PROC = CFG.processos[0]; // módulo ativo: Emissão de Notas Fiscais
  const P = PROC.parametros;
  const SIM = CFG.simulador;
  const STORE_KEY = "custeioABC.v1";

  /* ---------------- formatação ---------------- */
  const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const brl = (x) => (isFinite(x) ? BRL.format(x) : "—");
  const brl4 = (x) => (isFinite(x) ? "R$ " + num(x, 4) : "—");
  function num(x, casas = 2, min) {
    if (!isFinite(x)) return "—";
    return x.toLocaleString("pt-BR", { minimumFractionDigits: min ?? casas, maximumFractionDigits: casas });
  }
  const numV = (x, c = 2) => num(x, c, 0); // sem zeros à direita
  const pct = (x, c = 1) => (isFinite(x) ? num(x * 100, c) + "%" : "—");
  const csvNum = (x, c = 2) => (isFinite(x) ? x.toFixed(c).replace(".", ",") : "");
  function parseNum(s) {
    s = String(s).trim().replace(/\s|R\$|%/g, "");
    if (s === "") return NaN;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    return Number(s);
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  /* ---------------- estado ---------------- */
  function defaults() {
    const p = {}, origem = {}, sim = {};
    for (const k in P) { p[k] = P[k].padrao; origem[k] = { tipo: P[k].origem }; }
    for (const k in SIM) sim[k] = SIM[k].padrao;
    return { p, origem, sim };
  }
  function load() {
    const d = defaults();
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null"); } catch (e) { saved = null; }
    if (!saved || typeof saved !== "object") return { ...d, crono: [], tema: "sistema" };
    const pick = (src, base) => {
      const out = { ...base };
      if (src) for (const k in base) if (typeof src[k] === "number" && isFinite(src[k])) out[k] = src[k];
      return out;
    };
    const origem = { ...d.origem };
    if (saved.origem) for (const k in origem) if (saved.origem[k] && saved.origem[k].tipo) origem[k] = saved.origem[k];
    return {
      p: pick(saved.p, d.p),
      sim: pick(saved.sim, d.sim),
      origem,
      crono: Array.isArray(saved.crono) ? saved.crono : [],
      tema: saved.tema || "sistema"
    };
  }
  let S = load();
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(S)); } catch (e) { /* armazenamento indisponível */ }
  }

  /* ---------------- modelo ABC (seção 3.4) ---------------- */
  function calcular(p, sim) {
    const contratadas = p.licencasContratadas;
    const ocupadas = p.licencasOcupadas;
    const clientes = ocupadas; // clientesAtivos = licencasOcupadas
    const vida = Math.max(p.vidaClienteMeses, 1e-9);
    const notas = p.notasPorCliente;
    const aliq = p.aliquota / 100;
    const custoMinHumano = p.custoHora / 60;

    const custoLicenca = ocupadas > 0 ? p.mensalidadeNibo / ocupadas : NaN;
    const ociosas = Math.max(0, contratadas - ocupadas);
    const custoOciosoMes = contratadas > 0 ? ociosas * (p.mensalidadeNibo / contratadas) : 0;

    const claudeCustoMes = p.mensalidadeClaude * (p.pctDedicado / 100);
    const cadastrosPorMes = clientes / vida;
    const minClaudeMes = cadastrosPorMes * p.tClaudeCadastro + clientes * notas * p.tClaudeEmissao;
    const taxaClaudePorMin = minClaudeMes > 0 ? claudeCustoMes / minClaudeMes : 0;

    const claudeCadastro = p.tClaudeCadastro * taxaClaudePorMin;
    const claudeEmissao = p.tClaudeEmissao * taxaClaudePorMin;
    const humanoCadastro = p.tHumanoCadastro * custoMinHumano;
    const humanoEmissao = p.tHumanoEmissao * custoMinHumano;

    const custoCadastroPontual = claudeCadastro + humanoCadastro;
    const custoCadastroMensal = custoCadastroPontual / vida;
    const custoEmissaoPorNota = claudeEmissao + humanoEmissao;
    const custoEmissaoMensal = custoEmissaoPorNota * notas;

    const supHumano = sim.supHumanoMin * custoMinHumano;
    const supClaude = sim.supClaudeMin * taxaClaudePorMin;
    const suporteMensal = supHumano + supClaude;

    const lic = isFinite(custoLicenca) ? custoLicenca : 0;
    const comp = {
      A: { licenca: lic, claude: claudeCadastro / vida + claudeEmissao * notas, humano: humanoCadastro / vida + humanoEmissao * notas },
      B: { licenca: lic, claude: claudeCadastro / vida + supClaude, humano: humanoCadastro / vida + supHumano }
    };
    const custoA = custoLicenca + custoCadastroMensal + custoEmissaoMensal;
    const custoB = custoLicenca + custoCadastroMensal + suporteMensal;
    const custoA_semHumano = custoLicenca + comp.A.claude;
    const custoB_semHumano = custoLicenca + comp.B.claude;

    const fixos = p.mensalidadeNibo + claudeCustoMes;
    const cenario = (custo, variavel) => {
      const preco = sim.preco;
      const impostos = preco * aliq;
      const resultado = preco - impostos - custo;
      const contrib = preco - impostos - variavel;
      const m = sim.margemAlvo / 100;
      return {
        preco, impostos, custo, resultado, variavel,
        margem: preco > 0 ? resultado / preco : NaN,
        markup: custo > 0 ? (preco - custo) / custo : NaN,
        mensal: resultado * clientes,
        anual: resultado * clientes * 12,
        equilibrio: contrib > 0 ? fixos / contrib : NaN,
        precoMin: aliq < 1 ? custo / (1 - aliq) : NaN,
        precoAlvo: 1 - aliq - m > 0 ? custo / (1 - aliq - m) : NaN
      };
    };

    return {
      contratadas, ocupadas, clientes, vida, notas, aliq, custoMinHumano,
      custoLicenca, ociosas, custoOciosoMes, claudeCustoMes, cadastrosPorMes, minClaudeMes, taxaClaudePorMin,
      claudeCadastro, claudeEmissao, humanoCadastro, humanoEmissao,
      custoCadastroPontual, custoCadastroMensal, custoEmissaoPorNota, custoEmissaoMensal,
      supHumano, supClaude, suporteMensal, comp,
      custoA, custoB, custoA_semHumano, custoB_semHumano, fixos,
      A: cenario(custoA, comp.A.humano),
      B: cenario(custoB, comp.B.humano)
    };
  }
  // Registro de modelos: novos processos entram aqui com a sua função de cálculo.
  const MODELOS = { nfse: calcular };
  window.CUSTEIO_MODELOS = MODELOS;

  const resultadoCom = (preco) => {
    const r = calcular(S.p, { ...S.sim, preco });
    return { A: r.A, B: r.B };
  };

  /* ---------------- selos de origem ---------------- */
  function badge(k) {
    const o = S.origem[k] || { tipo: "informado" };
    if (o.tipo === "estimativa") return '<span class="badge est">Estimativa — validar na cronoanálise</span>';
    if (o.tipo === "preencher") return '<span class="badge fill">Preencher</span>';
    if (o.tipo === "medido") return `<span class="badge med">Medido · média de ${o.n} ${o.n === 1 ? "medição" : "medições"}</span>`;
    return '<span class="badge inf">Informado</span>';
  }

  /* ---------------- campos editáveis ---------------- */
  function fieldHTML(ns, k, def, extraClass = "") {
    const id = `${ns}-${k}`;
    const showBadge = ns === "p";
    return `<div class="field ${extraClass}">
      <label for="${id}">${esc(def.rotulo)}</label>
      <div class="input-wrap">${def.prefixo ? `<span class="pre">${def.prefixo}</span>` : ""}<input id="${id}" type="text" inputmode="decimal" data-key="${ns}.${k}">${def.unidade ? `<span class="unit">${esc(def.unidade)}</span>` : ""}</div>
      ${showBadge || def.nota ? `<div class="field-meta">${showBadge ? `<span data-badge="${k}">${badge(k)}</span>` : ""}${def.nota ? `<span class="note">${esc(def.nota)}</span>` : ""}</div>` : ""}
    </div>`;
  }
  function buildForms() {
    document.getElementById("form-param").innerHTML = PROC.grupos.map((g) =>
      `<fieldset class="param-group"><legend>${esc(g.titulo)}</legend>${g.campos.map((k) => fieldHTML("p", k, P[k])).join("")}</fieldset>`
    ).join("");
    document.getElementById("form-sim").innerHTML =
      fieldHTML("sim", "preco", SIM.preco, "hero") +
      fieldHTML("p", "aliquota", P.aliquota) +
      fieldHTML("sim", "margemAlvo", SIM.margemAlvo) +
      fieldHTML("sim", "supHumanoMin", SIM.supHumanoMin) +
      fieldHTML("sim", "supClaudeMin", SIM.supClaudeMin);
  }
  const defOf = (ns, k) => (ns === "p" ? P[k] : SIM[k]);
  function syncInputs(except) {
    document.querySelectorAll("[data-key]").forEach((el) => {
      if (el === except) return;
      const [ns, k] = el.dataset.key.split(".");
      el.value = numV(S[ns][k], 4);
      el.removeAttribute("aria-invalid");
    });
    document.querySelectorAll("[data-badge]").forEach((el) => { el.innerHTML = badge(el.dataset.badge); });
  }
  function onInput(e) {
    const el = e.target.closest("[data-key]");
    if (!el) return;
    const [ns, k] = el.dataset.key.split(".");
    const def = defOf(ns, k);
    let v = parseNum(el.value);
    const ok = isFinite(v) && v >= (def.min ?? -Infinity) && v <= (def.max ?? Infinity) && (!def.inteiro || Number.isInteger(v));
    if (!ok) { el.setAttribute("aria-invalid", "true"); return; }
    el.removeAttribute("aria-invalid");
    S[ns][k] = v;
    save();
    syncInputs(el);
    render();
  }
  document.addEventListener("input", onInput);
  document.addEventListener("focusout", (e) => {
    const el = e.target.closest && e.target.closest("[data-key]");
    if (el) { const [ns, k] = el.dataset.key.split("."); el.value = numV(S[ns][k], 4); el.removeAttribute("aria-invalid"); }
  });

  /* ---------------- alertas ---------------- */
  function renderAlertas(r) {
    const out = [];
    if (r.ocupadas <= 0) {
      out.push(`<div class="alert crit"><span class="ico">!</span><span><strong>Sem clientes ativos.</strong> Com 0 licenças ocupadas não há como distribuir a mensalidade do NIBO.</span></div>`);
    } else if (r.ociosas > 0) {
      out.push(`<div class="alert warn"><span class="ico">!</span><span><strong>Capacidade ociosa.</strong> ${r.ociosas} de ${r.contratadas} licenças NIBO estão livres: ${brl(r.custoOciosoMes)}/mês de estrutura sem cliente. A licença custa ${brl(r.custoLicenca)} por cliente, contra ${brl(r.contratadas > 0 ? S.p.mensalidadeNibo / r.contratadas : NaN)} com a base cheia.</span></div>`);
    }
    if (r.ocupadas > r.contratadas) {
      out.push(`<div class="alert crit"><span class="ico">!</span><span><strong>Acima da capacidade.</strong> ${r.ocupadas} clientes para ${r.contratadas} licenças contratadas. Revise o plano do NIBO.</span></div>`);
    }
    document.getElementById("alertas").innerHTML = out.join("");
  }

  /* ---------------- visão geral ---------------- */
  function margemChip(m) {
    const alvo = S.sim.margemAlvo / 100;
    const cls = !isFinite(m) ? "warn" : m < 0 ? "crit" : m < alvo ? "warn" : "good";
    const txt = !isFinite(m) ? "sem preço" : m < 0 ? "prejuízo" : m < alvo ? "abaixo da meta" : "na meta";
    return `<span class="chip ${cls}">${pct(m)} · ${txt}</span>`;
  }
  function renderVisao(r) {
    const occ = r.contratadas > 0 ? r.ocupadas / r.contratadas : 0;
    const occCls = occ > 1 ? "crit" : occ < 0.8 ? "warn" : "";
    document.getElementById("kpis").innerHTML = `
      <div class="kpi"><span class="kpi-label">Cenário A · escritório emite</span><span class="kpi-value">${brl(r.custoA)}</span><span class="kpi-sub">por cliente/mês · ${brl(r.custoA_semHumano)} só ferramentas</span></div>
      <div class="kpi"><span class="kpi-label">Cenário B · só o emissor</span><span class="kpi-value">${brl(r.custoB)}</span><span class="kpi-sub">por cliente/mês · ${brl(r.custoB_semHumano)} só ferramentas</span></div>
      <div class="kpi"><span class="kpi-label">Margem a ${brl(S.sim.preco)}/mês</span>
        <div class="kpi-pair"><span><span class="kpi-sub">A</span> ${margemChip(r.A.margem)}</span><span><span class="kpi-sub">B</span> ${margemChip(r.B.margem)}</span></div>
        <span class="kpi-sub">Meta: ${numV(S.sim.margemAlvo)}% · <a href="#simulador">ajustar preço</a></span></div>
      <div class="kpi"><span class="kpi-label">Ocupação de licenças</span><span class="kpi-value">${r.ocupadas}/${r.contratadas}</span>
        <div class="meter ${occCls}" role="img" aria-label="${pct(occ, 0)} ocupadas"><span style="width:${Math.min(occ, 1) * 100}%"></span></div>
        <span class="kpi-sub">${pct(occ, 0)} ocupadas · licença ${brl(r.custoLicenca)}/cliente</span></div>`;

    const share = r.custoA > 0 ? r.comp.A.licenca / r.custoA : NaN;
    const claudeA = r.comp.A.claude;
    const fullLic = (n) => (n > 0 ? brl(S.p.mensalidadeNibo / n) : "—");
    const ns = [10, 20, r.contratadas].filter((v, i, a) => v > 0 && a.indexOf(v) === i);
    document.getElementById("leitura").innerHTML = `
      <div class="panel-head"><h2>Leitura-chave</h2></div>
      <p>O custo é dominado pela <strong>licença NIBO</strong>: ${brl(r.comp.A.licenca)} de ${brl(r.custoA)}, cerca de <strong>${pct(share, 0)}</strong> do Cenário A. O Claude pesa ${brl(claudeA)} por cliente/mês com ${r.clientes} clientes.</p>
      <p>Com menos clientes a licença encarece: ${ns.map((n) => `${n} clientes → <strong>${fullLic(n)}</strong>`).join(" · ")}.</p>`;
  }

  /* ---------------- gráfico de barras empilhadas ---------------- */
  const SERIES = [
    { k: "licenca", nome: "Licença NIBO", cor: "var(--s1)" },
    { k: "claude", nome: "Claude", cor: "var(--s2)" },
    { k: "humano", nome: "Humano", cor: "var(--s3)" }
  ];
  function niceStep(max) {
    const raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    const f = raw / mag;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  }
  function chartSVG(r) {
    const rows = [
      { nome: "Cenário A", sub: "escritório emite", c: r.comp.A },
      { nome: "Cenário B", sub: "só o emissor", c: r.comp.B }
    ];
    const totals = rows.map((x) => x.c.licenca + x.c.claude + x.c.humano);
    const step = niceStep(Math.max(...totals, 1));
    const maxV = Math.ceil(Math.max(...totals, 1) / step) * step;
    const W = 640, L = 108, R = 76, top = 8, bh = 30, gap = 22, H = top + rows.length * (bh + gap) + 18;
    const x = (v) => L + (v / maxV) * (W - L - R);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Composição do custo por cliente por mês">`;
    for (let v = 0; v <= maxV + 1e-9; v += step) {
      s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 4}" y2="${H - 18}" stroke="var(--line)" stroke-width="1"/>`;
      s += `<text x="${x(v)}" y="${H - 4}" text-anchor="middle" font-size="11" fill="var(--muted)">${numV(v)}</text>`;
    }
    rows.forEach((row, i) => {
      const y = top + i * (bh + gap);
      s += `<text x="0" y="${y + 13}" font-size="13" font-weight="600" fill="var(--fg)">${row.nome}</text>`;
      s += `<text x="0" y="${y + 27}" font-size="11" fill="var(--muted)">${row.sub}</text>`;
      let acc = 0;
      const tot = totals[i];
      const visible = SERIES.filter((se) => row.c[se.k] > 0);
      visible.forEach((se, j) => {
        const v = row.c[se.k];
        const x0 = x(acc), x1 = x(acc + v);
        const last = j === visible.length - 1;
        const w = Math.max(0, x1 - x0 - (last ? 0 : 2));
        const rr = last ? Math.min(4, w) : 0;
        const d = `M${x0},${y} H${x0 + w - rr} Q${x0 + w},${y} ${x0 + w},${y + rr} V${y + bh - rr} Q${x0 + w},${y + bh} ${x0 + w - rr},${y + bh} H${x0} Z`;
        const tip = `${row.nome} · ${se.nome}: ${brl(v)} (${pct(tot > 0 ? v / tot : 0, 0)})`;
        s += `<path class="seg" tabindex="0" d="${d}" fill="${se.cor}" data-tip="${esc(tip)}"><title>${esc(tip)}</title></path>`;
        acc += v;
      });
      s += `<text x="${x(tot) + 8}" y="${y + bh / 2 + 4}" font-size="13" font-weight="600" fill="var(--fg)">${brl(tot)}</text>`;
    });
    s += `</svg>`;
    const legend = `<div class="legend">${SERIES.map((se) => `<span><i style="background:${se.cor}"></i>${se.nome}</span>`).join("")}</div>`;
    const table = `<div class="table-wrap"><table class="num-table"><thead><tr><th>Cenário</th>${SERIES.map((se) => `<th class="n">${se.nome}</th>`).join("")}<th class="n">Total</th></tr></thead><tbody>${rows.map((row, i) => `<tr><td>${row.nome}</td>${SERIES.map((se) => `<td class="n">${brl(row.c[se.k])}</td>`).join("")}<td class="n"><strong>${brl(totals[i])}</strong></td></tr>`).join("")}</tbody></table></div>`;
    return legend + s + table;
  }
  function renderCharts(r) { document.querySelectorAll("[data-chart]").forEach((el) => { el.innerHTML = chartSVG(r); }); }

  const tooltip = document.getElementById("tooltip");
  function showTip(el, cx, cy) {
    tooltip.textContent = el.dataset.tip;
    tooltip.hidden = false;
    const tw = tooltip.offsetWidth;
    tooltip.style.left = Math.max(8, Math.min(window.innerWidth - tw - 8, cx - tw / 2)) + "px";
    tooltip.style.top = Math.max(8, cy - 40) + "px";
  }
  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) showTip(el, e.clientX, e.clientY); else tooltip.hidden = true;
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el) { const b = el.getBoundingClientRect(); showTip(el, b.left + b.width / 2, b.top); }
  });
  document.addEventListener("focusout", () => { tooltip.hidden = true; });

  /* ---------------- custeio ABC passo a passo ---------------- */
  function linha(nome, sub, formula, subst, res, strong) {
    return `<div class="c-name${strong ? " strong" : ""}">${nome}${sub ? `<small>${sub}</small>` : ""}</div>
      <div class="c-formula${strong ? " strong" : ""}">${formula}<br><b>${subst}</b></div>
      <div class="c-res${strong ? " strong" : ""}">${res}</div>`;
  }
  function renderABC(r) {
    const p = S.p;
    const f2 = (x) => num(x, 2), f4 = (x) => num(x, 4);
    const blocos = [];
    blocos.push(`<div class="abc-block"><h2><span class="tag">RECURSOS</span>Custo dos recursos e taxas</h2><div class="calc">
      ${linha("A1 · Licença NIBO", "por licença ocupada", "mensalidadeNIBO ÷ licençasOcupadas", `${f2(p.mensalidadeNibo)} ÷ ${p.licencasOcupadas}`, brl(r.custoLicenca), true)}
      ${linha("Capacidade ociosa", `${r.ociosas} licença(s) livre(s)`, "(contratadas − ocupadas) × (mensalidadeNIBO ÷ contratadas)", `(${p.licencasContratadas} − ${p.licencasOcupadas}) × (${f2(p.mensalidadeNibo)} ÷ ${p.licencasContratadas})`, brl(r.custoOciosoMes) + "/mês")}
      ${linha("Claude dedicado", "custo mensal", "mensalidadeClaude × %dedicado", `${f2(p.mensalidadeClaude)} × ${numV(p.pctDedicado)}%`, brl(r.claudeCustoMes))}
      ${linha("Cadastros por mês", "direcionador de A2", "clientesAtivos ÷ vidaClienteMeses", `${r.clientes} ÷ ${numV(p.vidaClienteMeses)}`, f4(r.cadastrosPorMes))}
      ${linha("Minutos de Claude por mês", "", "cadastros/mês × tClaudeCadastro + clientes × notas × tClaudeEmissão", `${f4(r.cadastrosPorMes)} × ${numV(p.tClaudeCadastro)} + ${r.clientes} × ${numV(p.notasPorCliente)} × ${numV(p.tClaudeEmissao)}`, numV(r.minClaudeMes, 1) + " min")}
      ${linha("Taxa do Claude", "por minuto", "claudeCustoMes ÷ minClaudeMes", `${f2(r.claudeCustoMes)} ÷ ${numV(r.minClaudeMes, 1)}`, brl4(r.taxaClaudePorMin) + "/min", true)}
      ${linha("Taxa humana", "por minuto", "custoHora ÷ 60", `${f2(p.custoHora)} ÷ 60`, brl4(r.custoMinHumano) + "/min", true)}
    </div></div>`);
    blocos.push(`<div class="abc-block"><h2><span class="tag">A2</span>Cadastrar e configurar cliente</h2><div class="calc">
      ${linha("Claude", "por cadastro", "tClaudeCadastro × taxaClaude", `${numV(p.tClaudeCadastro)} min × ${f4(r.taxaClaudePorMin)}`, brl(r.claudeCadastro))}
      ${linha("Humano", "por cadastro", "tHumanoCadastro × taxaHumana", `${numV(p.tHumanoCadastro)} min × ${f4(r.custoMinHumano)}`, brl(r.humanoCadastro))}
      ${linha("Cadastro pontual", "por cliente novo", "Claude + humano", `${f2(r.claudeCadastro)} + ${f2(r.humanoCadastro)}`, brl(r.custoCadastroPontual), true)}
      ${linha("Cadastro amortizado", "por cliente/mês", "custoCadastroPontual ÷ vidaClienteMeses", `${f2(r.custoCadastroPontual)} ÷ ${numV(p.vidaClienteMeses)}`, brl(r.custoCadastroMensal), true)}
    </div></div>`);
    blocos.push(`<div class="abc-block"><h2><span class="tag">A3</span>Emitir nota</h2><div class="calc">
      ${linha("Claude", "por nota", "tClaudeEmissão × taxaClaude", `${numV(p.tClaudeEmissao)} min × ${f4(r.taxaClaudePorMin)}`, brl(r.claudeEmissao))}
      ${linha("Humano", "por nota", "tHumanoEmissão × taxaHumana", `${numV(p.tHumanoEmissao)} min × ${f4(r.custoMinHumano)}`, brl(r.humanoEmissao))}
      ${linha("Emissão por nota", "custo por nota emitida", "Claude + humano", `${f2(r.claudeEmissao)} + ${f2(r.humanoEmissao)}`, brl(r.custoEmissaoPorNota), true)}
      ${linha("Emissão mensal", "por cliente/mês", "custoEmissãoPorNota × notasPorCliente", `${f2(r.custoEmissaoPorNota)} × ${numV(p.notasPorCliente)}`, brl(r.custoEmissaoMensal), true)}
    </div></div>`);
    if (r.suporteMensal > 0) {
      blocos.push(`<div class="abc-block"><h2><span class="tag">SUP</span>Suporte ao cliente (Cenário B)</h2><div class="calc">
        ${linha("Suporte", "por cliente/mês", "minHumano × taxaHumana + minClaude × taxaClaude", `${numV(S.sim.supHumanoMin)} × ${f4(r.custoMinHumano)} + ${numV(S.sim.supClaudeMin)} × ${f4(r.taxaClaudePorMin)}`, brl(r.suporteMensal), true)}
      </div></div>`);
    }
    blocos.push(`<div class="abc-block"><h2><span class="tag">OBJETO</span>Custo por cliente ativo/mês</h2><div class="calc">
      ${linha("Cenário A", "escritório emite a nota", "A1 + A2 amortizado + A3 mensal", `${f2(r.custoLicenca)} + ${f2(r.custoCadastroMensal)} + ${f2(r.custoEmissaoMensal)}`, brl(r.custoA), true)}
      ${linha("Cenário A só ferramentas", "sem mão de obra humana", "A1 + Claude de A2 e A3", `${f2(r.custoLicenca)} + ${f2(r.comp.A.claude)}`, brl(r.custoA_semHumano))}
      ${linha("Cenário B", "só o emissor", "A1 + A2 amortizado + suporte", `${f2(r.custoLicenca)} + ${f2(r.custoCadastroMensal)} + ${f2(r.suporteMensal)}`, brl(r.custoB), true)}
      ${linha("Cenário B só ferramentas", "sem mão de obra humana", "A1 + Claude de A2 e do suporte", `${f2(r.custoLicenca)} + ${f2(r.comp.B.claude)}`, brl(r.custoB_semHumano))}
    </div></div>`);
    document.getElementById("abc-passos").innerHTML = blocos.join("");
  }

  /* ---------------- simulador ---------------- */
  function renderSim(r) {
    const td = (x, fmt = brl) => `<td class="n${x < 0 ? " neg" : ""}">${fmt(x)}</td>`;
    const be = (c) => isFinite(c.equilibrio) ? `${Math.ceil(c.equilibrio - 1e-9)} clientes<span class="hint">${num(c.equilibrio, 1)} exato${c.equilibrio > r.contratadas ? " · acima das licenças" : ""}</span>` : "não atinge<span class=\"hint\">preço não cobre o custo variável</span>";
    const A = r.A, B = r.B;
    document.getElementById("sim-tabela").innerHTML = `
      <thead><tr><th>Indicador</th><th class="n">Cenário A<small>serviço completo</small></th><th class="n">Cenário B<small>somente o emissor</small></th></tr></thead>
      <tbody>
        <tr><td>Receita por cliente/mês</td>${td(A.preco)}${td(B.preco)}</tr>
        <tr><td>(−) Impostos <span class="hint">${numV(S.p.aliquota)}% da receita</span></td>${td(-A.impostos)}${td(-B.impostos)}</tr>
        <tr><td>(−) Custo ABC por cliente/mês</td>${td(-A.custo)}${td(-B.custo)}</tr>
        <tr class="key sep"><td>= Resultado por cliente/mês</td>${td(A.resultado)}${td(B.resultado)}</tr>
        <tr class="key"><td>Margem</td>${td(A.margem, pct)}${td(B.margem, pct)}</tr>
        <tr><td>Markup</td>${td(A.markup, pct)}${td(B.markup, pct)}</tr>
        <tr class="sep"><td>Resultado mensal da carteira <span class="hint">${r.clientes} clientes</span></td>${td(A.mensal)}${td(B.mensal)}</tr>
        <tr><td>Resultado anual da carteira</td>${td(A.anual)}${td(B.anual)}</tr>
        <tr class="sep"><td>Ponto de equilíbrio <span class="hint">fixos ${brl(r.fixos)} ÷ (preço − impostos − variável)</span></td><td class="n">${be(A)}</td><td class="n">${be(B)}</td></tr>
        <tr><td>Preço mínimo <span class="hint">resultado = 0</span></td>${td(A.precoMin)}${td(B.precoMin)}</tr>
        <tr class="key"><td>Preço sugerido p/ margem de ${numV(S.sim.margemAlvo)}%</td>${td(A.precoAlvo)}${td(B.precoAlvo)}</tr>
      </tbody>`;

    const precos = [];
    for (let v = 20; v <= 80; v += 10) precos.push(v);
    const atual = S.sim.preco;
    if (!precos.includes(atual) && atual > 0) { precos.push(atual); precos.sort((a, b) => a - b); }
    document.getElementById("sens").innerHTML = `
      <thead><tr><th class="n">Preço</th><th class="n">Resultado A</th><th class="n">Margem A</th><th class="n">Resultado B</th><th class="n">Margem B</th></tr></thead>
      <tbody>${precos.map((v) => {
        const x = resultadoCom(v);
        return `<tr class="${v === atual ? "hl" : ""}"><td class="n">${brl(v)}${v === atual ? " ◂" : ""}</td>${td(x.A.resultado)}${td(x.A.margem, pct)}${td(x.B.resultado)}${td(x.B.margem, pct)}</tr>`;
      }).join("")}</tbody>`;
  }

  /* ---------------- exportação ---------------- */
  function linhasExport(r) {
    const vida = numV(S.p.vidaClienteMeses);
    const rows = [
      ["A1 - Manter licença NIBO", "licença ocupada", r.custoLicenca, r.custoLicenca],
      ["A2 - Cadastrar e configurar cliente", `cadastro (÷ ${vida} meses de vida)`, r.custoCadastroPontual, r.custoCadastroMensal],
      ["A3 - Emitir nota", `nota emitida (${numV(S.p.notasPorCliente)}/cliente/mês)`, r.custoEmissaoPorNota, r.custoEmissaoMensal]
    ];
    if (r.suporteMensal > 0) rows.push(["Suporte ao cliente (Cenário B)", "minuto de suporte", r.suporteMensal, r.suporteMensal]);
    rows.push(["TOTAL Cenário A - escritório emite", "cliente ativo/mês", "", r.custoA]);
    rows.push(["TOTAL Cenário B - somente o emissor", "cliente ativo/mês", "", r.custoB]);
    return rows;
  }
  function csvExport(r) {
    const head = "atividade;direcionador;custo_unitario;custo_cliente_mes";
    const q = (s) => (/[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
    return [head, ...linhasExport(r).map((l) => [q(l[0]), q(l[1]), l[2] === "" ? "" : csvNum(l[2], 4), csvNum(l[3], 4)].join(";"))].join("\r\n");
  }
  function renderExport(r) {
    document.getElementById("exp-tabela").innerHTML = `
      <thead><tr><th>Atividade</th><th>Direcionador</th><th class="n">Custo unitário</th><th class="n">Custo cliente/mês</th></tr></thead>
      <tbody>${linhasExport(r).map((l) => `<tr class="${l[0].startsWith("TOTAL") ? "total" : ""}"><td>${esc(l[0])}</td><td>${esc(l[1])}</td><td class="n">${l[2] === "" ? "" : brl(l[2])}</td><td class="n">${brl(l[3])}</td></tr>`).join("")}</tbody>`;
    document.getElementById("csv-text").value = csvExport(r);
  }
  function download(nome, texto) {
    const blob = new Blob(["﻿" + texto], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  const hoje = () => new Date().toISOString().slice(0, 10);
  document.getElementById("btn-csv").addEventListener("click", () => download(`custeio_abc_nfse_${hoje()}.csv`, csvExport(calcular(S.p, S.sim))));
  document.getElementById("btn-print").addEventListener("click", () => window.print());
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    const ta = document.getElementById(b.dataset.copy);
    const msg = document.getElementById("copy-msg");
    const done = (t) => { b.textContent = t; setTimeout(() => { b.textContent = "Copiar CSV"; }, 1800); if (msg && b.closest("#exportar")) msg.textContent = ""; };
    const fallback = () => { ta.focus(); ta.select(); done("Texto selecionado: use Ctrl+C"); };
    try {
      navigator.clipboard.writeText(ta.value).then(() => done("Copiado"), fallback);
    } catch (err) { fallback(); }
  });

  // Dentro de um frame (visualizador) download e impressão ficam bloqueados.
  const framed = (() => { try { return window.self !== window.top; } catch (e) { return true; } })();
  document.querySelectorAll("[data-only-top]").forEach((el) => { el.hidden = framed; });
  document.querySelectorAll("[data-only-framed]").forEach((el) => { el.hidden = !framed; });

  /* ---------------- cronoanálise ---------------- */
  function stats(vals) {
    const n = vals.length;
    if (!n) return null;
    const media = vals.reduce((a, b) => a + b, 0) / n;
    const dp = n > 1 ? Math.sqrt(vals.reduce((a, b) => a + (b - media) ** 2, 0) / (n - 1)) : 0;
    return { n, media, min: Math.min(...vals), max: Math.max(...vals), dp };
  }
  const FASES = { cadastro: "Cadastro", emissao: "Emissão" };
  function renderCrono() {
    const box = document.getElementById("crono-stats");
    box.innerHTML = Object.keys(FASES).map((f) => {
      const ms = S.crono.filter((m) => m.fase === f);
      const sc = stats(ms.map((m) => m.claude)), sh = stats(ms.map((m) => m.humano));
      const kC = f === "cadastro" ? "tClaudeCadastro" : "tClaudeEmissao";
      const kH = f === "cadastro" ? "tHumanoCadastro" : "tHumanoEmissao";
      const linhaS = (rot, s, k) => `<tr><td>${rot}</td><td class="n">${s ? numV(s.media, 1) : "—"}</td><td class="n">${s ? numV(s.min, 1) : "—"}</td><td class="n">${s ? numV(s.max, 1) : "—"}</td><td class="n">${s ? numV(s.dp, 2) : "—"}</td><td class="n">${numV(S.p[k], 2)}</td></tr>`;
      return `<div class="panel stat-card"><h3>${FASES[f]} <span class="muted">${ms.length} ${ms.length === 1 ? "medição" : "medições"}</span></h3>
        <div class="table-wrap"><table class="num-table"><thead><tr><th>Recurso (min)</th><th class="n">Média</th><th class="n">Mín</th><th class="n">Máx</th><th class="n">Desvio</th><th class="n">Em uso</th></tr></thead>
        <tbody>${linhaS("Claude", sc, kC)}${linhaS("Humano", sh, kH)}</tbody></table></div></div>`;
    }).join("");

    const t = document.getElementById("crono-tabela");
    if (!S.crono.length) {
      t.innerHTML = `<tbody><tr><td><div class="empty">Nenhuma medição ainda. Cronometre um cadastro ou uma emissão e registre acima: data, cliente, fase e os minutos de Claude e de trabalho humano.</div></td></tr></tbody>`;
    } else {
      const ord = S.crono.map((m, i) => ({ ...m, i })).sort((a, b) => (a.data < b.data ? 1 : a.data > b.data ? -1 : b.i - a.i));
      t.innerHTML = `<thead><tr><th>Data</th><th>Cliente</th><th>Fase</th><th class="n">Min Claude</th><th class="n">Min humano</th><th></th></tr></thead>
        <tbody>${ord.map((m) => `<tr><td>${esc(m.data.split("-").reverse().join("/"))}</td><td>${esc(m.cliente)}</td><td>${FASES[m.fase]}</td><td class="n">${numV(m.claude, 1)}</td><td class="n">${numV(m.humano, 1)}</td><td><button type="button" class="del" data-del="${m.i}" aria-label="Excluir medição">Excluir</button></td></tr>`).join("")}</tbody>`;
    }
    document.getElementById("btn-usar-media").disabled = !S.crono.length;
    const csvBox = document.getElementById("crono-csv-box");
    if (!csvBox.hidden) document.getElementById("crono-csv-text").value = csvCrono();
  }
  function csvCrono() {
    const q = (s) => (/[;"\n]/.test(s) ? `"${String(s).replace(/"/g, '""')}"` : s);
    return ["data;cliente;fase;min_claude;min_humano", ...S.crono.map((m) => [m.data, q(m.cliente), m.fase, csvNum(m.claude, 2), csvNum(m.humano, 2)].join(";"))].join("\r\n");
  }
  document.getElementById("c-data").value = hoje();
  document.getElementById("form-crono").addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = document.getElementById("crono-msg");
    const data = document.getElementById("c-data").value;
    const cliente = document.getElementById("c-cliente").value.trim();
    const fase = document.getElementById("c-fase").value;
    const claude = parseNum(document.getElementById("c-claude").value);
    const humano = parseNum(document.getElementById("c-humano").value);
    if (!data || !cliente) { msg.textContent = "Preencha a data e o cliente."; return; }
    if (!(claude >= 0) || !(humano >= 0)) { msg.textContent = "Os minutos precisam ser números iguais ou maiores que zero (use vírgula para decimais)."; return; }
    msg.textContent = "";
    S.crono.push({ data, cliente, fase, claude, humano });
    save();
    document.getElementById("c-claude").value = "";
    document.getElementById("c-humano").value = "";
    document.getElementById("c-claude").focus();
    renderCrono();
  });
  document.getElementById("crono-tabela").addEventListener("click", (e) => {
    const b = e.target.closest("[data-del]");
    if (!b) return;
    S.crono.splice(Number(b.dataset.del), 1);
    save();
    renderCrono();
  });
  document.getElementById("btn-usar-media").addEventListener("click", () => {
    const aplicados = [];
    for (const f of Object.keys(FASES)) {
      const ms = S.crono.filter((m) => m.fase === f);
      if (!ms.length) continue;
      const kC = f === "cadastro" ? "tClaudeCadastro" : "tClaudeEmissao";
      const kH = f === "cadastro" ? "tHumanoCadastro" : "tHumanoEmissao";
      S.p[kC] = Math.round(stats(ms.map((m) => m.claude)).media * 100) / 100;
      S.p[kH] = Math.round(stats(ms.map((m) => m.humano)).media * 100) / 100;
      S.origem[kC] = { tipo: "medido", n: ms.length };
      S.origem[kH] = { tipo: "medido", n: ms.length };
      aplicados.push(FASES[f].toLowerCase());
    }
    save();
    syncInputs();
    render();
    document.getElementById("crono-aplicar-msg").textContent = aplicados.length ? `Médias de ${aplicados.join(" e ")} aplicadas aos parâmetros.` : "";
  });
  document.getElementById("btn-crono-csv").addEventListener("click", () => {
    if (framed) {
      const box = document.getElementById("crono-csv-box");
      box.hidden = false;
      document.getElementById("crono-csv-text").value = csvCrono();
      box.scrollIntoView({ block: "nearest" });
    } else {
      download(`cronoanalise_nfse_${hoje()}.csv`, csvCrono());
    }
  });

  /* ---------------- novo processo ---------------- */
  document.getElementById("futuros").innerHTML = CFG.futuros.map((f) => `
    <div class="futuro"><div class="row" style="justify-content:space-between"><h3>${esc(f.nome)}</h3><span class="badge inf">A modelar</span></div>
      <dl><dt>Recursos</dt><dd>${f.recursos.map(esc).join(" · ")}</dd>
      <dt>Atividades</dt><dd>${f.atividades.map(esc).join(" · ")}</dd>
      <dt>Direcionador principal</dt><dd>${esc(f.direcionador)}</dd>
      <dt>Objeto de custo</dt><dd>${esc(f.objeto)}</dd></dl></div>`).join("");

  /* ---------------- restaurar / tema ---------------- */
  const conf = document.getElementById("confirm-restaurar");
  document.getElementById("btn-restaurar").addEventListener("click", () => { conf.hidden = !conf.hidden; });
  document.getElementById("btn-restaurar-cancel").addEventListener("click", () => { conf.hidden = true; });
  document.getElementById("btn-restaurar-ok").addEventListener("click", () => {
    const d = defaults();
    S.p = d.p; S.origem = d.origem; S.sim = d.sim;
    save();
    conf.hidden = true;
    syncInputs();
    render();
  });
  const TEMAS = ["sistema", "claro", "escuro"];
  function aplicarTema() {
    const root = document.documentElement;
    if (S.tema === "claro") root.setAttribute("data-theme", "light");
    else if (S.tema === "escuro") root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");
    document.getElementById("btn-tema").textContent = "Tema: " + S.tema;
  }
  document.getElementById("btn-tema").addEventListener("click", () => {
    S.tema = TEMAS[(TEMAS.indexOf(S.tema) + 1) % TEMAS.length];
    save();
    aplicarTema();
  });

  /* ---------------- navegação ---------------- */
  const VIEWS = Array.from(document.querySelectorAll("[data-view]")).map((s) => s.id);
  function route() {
    const h = location.hash.replace("#", "");
    const id = VIEWS.includes(h) ? h : "visao";
    document.querySelectorAll("[data-view]").forEach((s) => { s.hidden = s.id !== id; });
    document.querySelectorAll(".nav a").forEach((a) => {
      if (a.getAttribute("href") === "#" + id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    const cur = document.querySelector(".nav a[aria-current]");
    if (cur && cur.scrollIntoView && window.matchMedia("(max-width: 860px)").matches) cur.scrollIntoView({ block: "nearest", inline: "center" });
  }
  window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

  /* ---------------- render ---------------- */
  function render() {
    const r = calcular(S.p, S.sim);
    renderAlertas(r);
    renderVisao(r);
    renderCharts(r);
    renderABC(r);
    renderSim(r);
    renderExport(r);
    renderCrono();
  }

  buildForms();
  syncInputs();
  if (S.tema !== "sistema") aplicarTema(); else document.getElementById("btn-tema").textContent = "Tema: sistema";
  route();
  render();

  // Exposto para testes de aceitação no console: CUSTEIO_TESTE()
  window.CUSTEIO_TESTE = () => calcular(defaults().p, defaults().sim);
})();
