/*
 * Parâmetros padrão dos custeios ABC do escritório.
 *
 * Cada processo segue o mesmo modelo: recursos -> atividades -> objeto de custo.
 * `origem` de cada parâmetro:
 *   "informado"  valor passado pelo escritório
 *   "estimativa" valor assumido; aparece com o selo amarelo até ser medido
 *   "preencher"  campo que o escritório precisa preencher (ex.: alíquota)
 * A origem "medido" é atribuída pelo módulo de cronoanálise.
 */
window.CUSTEIO = {
  versao: 1,

  processos: [
    {
      id: "nfse",
      nome: "Emissão de Notas Fiscais",
      ferramentas: "NIBO + Claude Pro",
      status: "ativo",
      grupos: [
        { titulo: "NIBO (emissor de notas)", campos: ["mensalidadeNibo", "licencasContratadas", "licencasOcupadas"] },
        { titulo: "Claude Pro", campos: ["mensalidadeClaude", "pctDedicado"] },
        { titulo: "Tempos por atividade", campos: ["tClaudeCadastro", "tHumanoCadastro", "tClaudeEmissao", "tHumanoEmissao"] },
        { titulo: "Mão de obra e carteira", campos: ["custoHora", "notasPorCliente", "vidaClienteMeses"] },
        { titulo: "Tributos", campos: ["aliquota"] }
      ],
      parametros: {
        mensalidadeNibo:     { rotulo: "Mensalidade NIBO", prefixo: "R$", unidade: "/mês", padrao: 250, origem: "informado", min: 0 },
        licencasContratadas: { rotulo: "Licenças contratadas", unidade: "licenças", padrao: 31, origem: "informado", min: 0, inteiro: true },
        licencasOcupadas:    { rotulo: "Licenças ocupadas (clientes ativos)", unidade: "clientes", padrao: 31, origem: "estimativa", min: 0, inteiro: true,
                               nota: "Assume uso total das licenças." },
        mensalidadeClaude:   { rotulo: "Mensalidade Claude Pro", prefixo: "R$", unidade: "/mês", padrao: 100, origem: "informado", min: 0 },
        pctDedicado:         { rotulo: "Parte do Claude Pro usada neste processo", unidade: "%", padrao: 100, origem: "estimativa", min: 0, max: 100,
                               nota: "Pior caso. Reduza se o Claude atende outras atividades." },
        tClaudeCadastro:     { rotulo: "Tempo Claude — cadastro", unidade: "min", padrao: 60, origem: "informado", min: 0, fase: "cadastro", recurso: "claude",
                               nota: "Pior caso informado, não medido." },
        tHumanoCadastro:     { rotulo: "Tempo humano — cadastro", unidade: "min", padrao: 10, origem: "estimativa", min: 0, fase: "cadastro", recurso: "humano",
                               nota: "Certificado + licença + conferência." },
        tClaudeEmissao:      { rotulo: "Tempo Claude — emissão", unidade: "min", padrao: 5, origem: "informado", min: 0, fase: "emissao", recurso: "claude",
                               nota: "Pior caso informado, não medido." },
        tHumanoEmissao:      { rotulo: "Tempo humano — emissão", unidade: "min", padrao: 3, origem: "estimativa", min: 0, fase: "emissao", recurso: "humano",
                               nota: "Enviar tomador e valor + conferir." },
        custoHora:           { rotulo: "Custo da hora humana", prefixo: "R$", unidade: "/h", padrao: 40, origem: "estimativa", min: 0,
                               nota: "Substituir pelo custo real (salário + encargos ÷ horas)." },
        notasPorCliente:     { rotulo: "Notas por cliente por mês", unidade: "notas", padrao: 1, origem: "estimativa", min: 0 },
        vidaClienteMeses:    { rotulo: "Vida média do cliente", unidade: "meses", padrao: 12, origem: "estimativa", min: 1,
                               nota: "Prazo usado para amortizar o cadastro." },
        aliquota:            { rotulo: "Impostos sobre a receita", unidade: "%", padrao: 0, origem: "preencher", min: 0, max: 99,
                               nota: "Simples Nacional / ISS." }
      }
    }
  ],

  // Campos do simulador de preço (também salvos no navegador)
  simulador: {
    preco:        { rotulo: "Preço de venda desejado", prefixo: "R$", unidade: "/mês", padrao: 40, min: 0 },
    margemAlvo:   { rotulo: "Margem-alvo", unidade: "%", padrao: 30, min: 0, max: 99 },
    supHumanoMin: { rotulo: "Suporte humano por cliente (Cenário B)", unidade: "min/mês", padrao: 0, min: 0 },
    supClaudeMin: { rotulo: "Suporte Claude por cliente (Cenário B)", unidade: "min/mês", padrao: 0, min: 0 }
  },

  // Próximos custeios: mesmo modelo recursos -> atividades -> objeto de custo
  futuros: [
    {
      nome: "Folha de pagamento",
      recursos: ["Sistema de folha", "Mão de obra do DP"],
      atividades: ["Lançar eventos do mês", "Calcular e conferir a folha", "Gerar guias (FGTS, INSS)"],
      direcionador: "nº de funcionários do cliente",
      objeto: "cliente/mês"
    },
    {
      nome: "Abertura de empresa",
      recursos: ["Taxas da Junta e da prefeitura", "Certificado digital", "Mão de obra societária"],
      atividades: ["Viabilidade e consulta de nome", "Contrato social e registro", "Inscrições e alvarás"],
      direcionador: "nº de aberturas",
      objeto: "abertura (pontual)"
    },
    {
      nome: "Contabilidade mensal",
      recursos: ["Sistema contábil", "Mão de obra contábil"],
      atividades: ["Importar extratos e notas", "Conciliar contas", "Apurar impostos e entregar obrigações"],
      direcionador: "nº de lançamentos do cliente",
      objeto: "cliente/mês"
    }
  ]
};
