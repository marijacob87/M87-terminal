# AGENTS.md

## Projeto

M87 TERMINAL

Aplicação desktop desenvolvida em Python + PySide6 para macOS.

O objetivo do software é acelerar tarefas de pré-impressão e produção gráfica através de um terminal de comandos e ferramentas especializadas.

## Prioridades

Toda alteração deve respeitar esta ordem:

1. Estabilidade
2. Simplicidade
3. Performance
4. Consistência visual
5. Facilidade de manutenção

Nunca sacrificar estabilidade por novas funcionalidades.

## Filosofia

O M87 Terminal deve parecer um aplicativo profissional nativo do macOS.

O usuário trabalha nele durante todo o expediente.

Cada clique economizado importa.

Sempre preferir:

- automação
- atalhos
- reutilização de código
- interface limpa
- poucas janelas

Nunca criar funcionalidades duplicadas.

## Interface

A aparência atual deve ser preservada.

Não alterar sem autorização explícita:

- cores
- fontes
- espaçamentos
- margens
- ícones
- tamanho das linhas
- comportamento das janelas

Toda melhoria visual deve ser incremental.

## Arquitetura

Sempre reutilizar componentes existentes.

Evitar criar novas janelas.

Se existir uma janela semelhante, adicionar nova aba.

Exemplo:

`ToolsDialog` compartilha a mesma janela entre `IMP`, `GEO`, `MON` e `BAR`.

## Organização

Separação obrigatória:

- `ui/`: interface
- `core/`: lógica
- `scripts/`: processamento externo
- `assets/`: ícones
- `utils/`: funções auxiliares

Nunca misturar interface com processamento pesado.

## Código

Preferências:

- `snake_case`
- funções pequenas
- responsabilidade única
- evitar arquivos gigantes
- comentários apenas quando realmente necessários

## Convenções

Sempre:

- reutilizar widgets
- reutilizar diálogos
- reutilizar estilos

Nunca copiar código inteiro.

Criar funções reutilizáveis.

## Performance

Evitar:

- loops desnecessários
- reprocessar PDFs
- abrir arquivos repetidamente

Sempre reutilizar resultados quando possível.

## Segurança

Nunca apagar arquivos automaticamente sem confirmação.

Nunca sobrescrever PDFs sem autorização.

Sempre utilizar “Salvar Como” quando existir risco.

## PDF

Todo processamento deve preservar:

- `MediaBox`
- `TrimBox`
- `BleedBox`
- `ArtBox` (quando existir)
- resolução
- perfis ICC
- separações
- metadados, sempre que possível

## Interface Terminal

Nunca alterar sem autorização:

- atalhos existentes
- ordem dos comandos
- cores
- fonte
- comportamento do prompt

## Antes de modificar qualquer módulo

Perguntar:

- Existe código semelhante?
- Existe função reutilizável?
- Existe janela compartilhada?
- Existe componente pronto?

Se sim, reutilizar.

Nunca reinventar.

## Objetivo final

Código pequeno.

Código organizado.

Código previsível.

Código reutilizável.

Sempre preservar a experiência do usuário.
