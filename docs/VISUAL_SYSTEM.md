# Sistema visual

Este documento é a referência canônica da interface do M87 Terminal. Ele
registra o visual aprovado sem ampliar ou redesenhar funcionalidades.

Os valores executáveis ficam em `ui/design_tokens.py`. Os componentes
compartilhados das ferramentas ficam em `ui/tool_design.py`. Valores repetidos
não devem ser copiados para cada aba.

## Princípios

1. estabilidade antes de aparência;
2. aparência profissional, compacta e nativa do macOS;
3. mesma função, mesmo componente, tamanho, cor e posição;
4. estados devem ser claros sem adicionar ruído;
5. alterações globais começam nos tokens ou componentes compartilhados.

## Paleta

| Papel | Valor | Uso |
| --- | --- | --- |
| fundo principal | `#050607` | abas, controles e área ao redor da prévia |
| destaque | `#FFC400` | aba ativa, títulos e ações primárias |
| destaque em hover | `#FFF0A0` | resposta de ações destacadas |
| texto principal | branco 88% | conteúdo editável e valores |
| texto secundário | branco 68% | ações e informações auxiliares |
| texto discreto | branco 43% | rótulos e metadados |
| texto desabilitado | branco 24% | controles indisponíveis |
| cartão | branco 2,5% | agrupamentos de controles |
| campo | branco 7% | inputs e seletores |
| borda discreta | branco 8% | cartões e campos |

O amarelo é semântico: destaque ativo ou ação principal. Não deve decorar
controles comuns nem substituir o cinza do estado desabilitado.

## Tipografia

- família: JetBrains Mono, herdada da aplicação;
- título de cartão: 9 px, peso 700, amarelo, espaçamento 0,7 px;
- rótulo de campo: 8 px, branco 43%;
- textos de botões permanecem centralizados vertical e horizontalmente;
- não usar outra família ou capitalização em uma aba isolada.

## Métricas das ferramentas

| Elemento | Padrão |
| --- | --- |
| coluna lateral | 400 px |
| margens da página | 14 / 12 / 14 / 12 px |
| espaço vertical da página | 9 px |
| espaço entre colunas | 12 px |
| margens internas do cartão | 11 / 8 / 11 / 9 px |
| espaço interno do cartão | 7 px |
| campo de medida ou texto | 26 px de altura |
| botão comum | 26 px de altura |
| símbolo de inversão de medidas | 15 px, peso 500 |
| chip | 25 px de altura |
| barra de prévia | 24 px de altura |
| botão Abrir PDF | 38 px de altura |
| ação do rodapé | 136 × 28 px |
| raio de controle | 4 px |
| raio de cartão | 7 px |

## Estrutura das cinco abas

A ordem fixa é: Organizar Páginas, Geometria, Imposição, Montagem e EAN-13.
As ferramentas de PDF compartilham o mesmo arquivo ativo. A navegação entre
abas usa `⌘←` e `⌘→`.

ORG, GEO e IMP seguem esta composição:

1. cartão Arquivo no topo esquerdo, com o mesmo botão Abrir PDF;
2. nome, TrimBox e quantidade de páginas quando carregado;
3. controles específicos abaixo, sem alterar a largura da coluna;
4. barra de página, rotação e zoom na mesma posição acima da prévia;
5. prévia central;
6. Restaurar original à esquerda do rodapé;
7. Imprimir e Salvar como à direita, com medidas idênticas.

Montagem mantém o fluxo de cálculo sem PDF e usa Limpar no rodapé. EAN-13
mantém suas subabas de código, sem simular um documento PDF.

## Estados

### Sem PDF

- somente Abrir PDF e a navegação entre abas permanecem disponíveis;
- controles dependentes do documento ficam desabilitados;
- ícones, textos e bordas desabilitados usam cinza, nunca branco ou amarelo;
- a prévia exibe apenas “Arraste um PDF para visualizar”, centralizado com o
  mesmo tamanho, cor e posição em ORG, GEO e IMP;
- o cartão Arquivo mostra “Nenhum PDF carregado”.

### Com PDF

- o cartão Arquivo mostra nome, TrimBox e quantidade de páginas;
- os controles válidos são habilitados sem mudar de tamanho ou posição;
- ações destrutivas ou que sobrescrevam conteúdo exigem confirmação;
- Salvar como nunca sobrescreve silenciosamente o original.

### Checkbox e radio button

Usam desenho inspirado no macOS, com indicador a 60% da área nativa. O estado
selecionado usa `#FFC400`; desabilitado permanece cinza. Tamanho, alinhamento e
espaço de 6 px até o texto são iguais em todas as abas.

## Componentes compartilhados

- `ToolPreviewToolbar`: página, rotação e zoom;
- `ToolActionBar`: ações fixas do rodapé;
- cartão Arquivo e resumo de PDF;
- campos de medida e botão de inversão;
- mensagens de prévia vazia;
- estilo de checkbox e radio button.

Uma aba não deve reproduzir esses componentes com QSS ou geometria próprios.

## Janelas auxiliares

Janelas de referência, checklist, biblioteca de formatos, informações de PDF,
registro de impressão e renomeação preservam seu fluxo atual. Ao receberem
novos controles, devem usar a paleta, tipografia, alturas e estados deste
documento. Uma exceção deve ser intencional e registrada no código.

## Checklist de revisão visual

- [ ] nenhum valor global foi duplicado fora de `design_tokens.py`;
- [ ] componentes existentes foram reutilizados;
- [ ] alturas, margens e alinhamentos coincidem entre abas;
- [ ] estados vazio, carregando, erro, desabilitado e ativo são legíveis;
- [ ] teclado, foco, hover e clique continuam funcionando;
- [ ] textos e ícones estão centralizados;
- [ ] foi feita inspeção manual no macOS nas cinco abas, com e sem PDF;
- [ ] os testes automatizados continuam passando.
