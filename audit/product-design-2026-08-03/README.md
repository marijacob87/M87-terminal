# Auditoria visual — M87 Terminal

Data: 03/08/2026

## Escopo

Auditoria combinada de UX e riscos visuais de acessibilidade, baseada nas seis
capturas fornecidas pelo utilizador: terminal principal e estados iniciais das
cinco ferramentas da janela compartilhada.

## Veredito

O M87 já possui uma identidade forte, consistente e adequada a um utilitário de
produção. As melhorias de maior impacto são tornar estados vazios mais úteis,
aproximar controles do conteúdo que afetam, melhorar a diferenciação entre
ações disponíveis e indisponíveis e ampliar a operabilidade por teclado.

## Prioridades

1. Transformar os grandes estados vazios em zonas de entrada claramente
   acionáveis, com instrução curta e formatos aceitos.
2. Ocultar ou desabilitar grupos que não podem ser usados antes de carregar um
   PDF, evitando painéis visualmente ativos sem efeito.
3. Padronizar a hierarquia das ações: primária, secundária, destrutiva e
   indisponível.
4. Tornar controles pequenos e ícones acessíveis por teclado, com foco visível e
   nomes acessíveis.
5. Aumentar o contraste dos textos auxiliares cinza sem alterar a identidade
   preta, amarela e metálica.

## Limites

As capturas não comprovam ordem de Tab, foco, atalhos, leitores de tela,
contraste medido, estados de erro, carregamento ou processamento. Esses pontos
precisam de teste interativo no macOS.

## Fluxo unificado proposto para as abas

### Estrutura comum

1. Entrada e estado do documento ficam no topo ou no primeiro bloco à esquerda.
2. Edição ocupa a lateral; prévia ocupa o centro.
3. Limpar ou restaurar fica no canto inferior esquerdo.
4. A ação que produz um arquivo fica sempre no canto inferior direito.
5. Fechar a janela acontece apenas pelo `×` global; as abas não usam `OK` ou
   `FECHAR` para encerrar.
6. Ações indisponíveis permanecem visíveis, porém desabilitadas.

### Vocabulário

- `ABRIR PDF`: inicia o fluxo; depois de carregado passa a `TROCAR PDF`.
- `REMOVER PDF`: descarrega o documento sem fechar a ferramenta.
- `LIMPAR`: reinicia campos de uma ferramenta sem documento.
- `RESTAURAR ORIGINAL`: desfaz todas as alterações do documento carregado.
- `SALVAR COMO…`: sempre abre escolha de destino e nunca sobrescreve a origem.
- `PROCESSAR LOTE…`: fluxo de múltiplos arquivos; deve pedir pasta de destino.
- `COPIAR`: envia o resultado à área de transferência.

### Aplicação por aba

- Organizar: `ABRIR/TROCAR PDF` no topo, `SALVAR COMO…` no canto inferior
  direito e controles desabilitados no estado vazio.
- Geometria: mesma entrada de PDF de Organizar; `RESTAURAR ORIGINAL` à esquerda
  e `SALVAR COMO…` à direita.
- Imposição: entrada de um ou vários PDFs no topo; `REMOVER PDF` perto do estado
  do arquivo; `SALVAR COMO…` para arquivo único e `PROCESSAR LOTE…` para lote.
- Montagem: não recebe PDF; calcula a partir de medidas. Mantém `LIMPAR` à
  esquerda e remove o botão `OK`, usando apenas o fechamento global.
- Códigos: entrada depende da subaba. Mantém `LIMPAR` à esquerda, `COPIAR` como
  ação secundária e `BAIXAR SVG…` como saída primária; remove `FECHAR`.
