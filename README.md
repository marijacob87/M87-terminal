cd "/Users/.../m87_terminal"
source .venv/bin/activate
git pull
code .

----------------------------------
Quando terminar de programar:
git add .
git commit -m "RENOMEAR FUNCIONANDO"
git push

----------------------------------
No outro computador:
cd "/Users/.../m87_terminal"
source .venv/bin/activate
git pull
code .


# M87 TERM

M87 TERM é um painel pessoal de automações para macOS, com visual inspirado em terminal clássico.

A ideia não é substituir o Terminal, Alfred ou Raycast.  
É criar um painel fixo, leve e minimalista com os atalhos mais usados no dia a dia.

O app permite executar comandos digitando códigos curtos, como:

BM
MR
AD
RR

ou clicando diretamente na lista.

---

## Objetivo

Reduzir cliques repetitivos e centralizar ações frequentes em uma interface única.

Exemplos:

- bloquear Mac
- abrir pastas
- abrir apps
- executar Atalhos do macOS
- reiniciar o próprio M87 TERM
- futuramente executar scripts de pré-impressão, PDF, Finder e Adobe

---

## Filosofia visual

- fundo preto translúcido
- fonte monoespaçada
- verde terminal
- amarelo discreto no hover
- sem ícones
- sem popups
- sem menus escondidos
- tudo rápido, visível e direto

---

## Estrutura dos arquivos

main.py  
Arquivo de entrada. Inicia o app.

config.py  
Configurações gerais: tamanho padrão, fonte, tempos de atualização, caminhos e constantes.

styles.py  
CSS/estilo visual do app.

widgets.py  
Componentes reutilizáveis da interface, como a linha clicável de comando.

terminal_input.py  
Campo de entrada com visual de terminal e cursor bloco verde piscante.

status.py  
Coleta dados para a barra de status: data, hora, Wi-Fi, bateria, clima e CPU.

state.py  
Salva e carrega posição/tamanho da janela usando state.json.

state.json  
Arquivo criado automaticamente para lembrar onde e em que tamanho a janela ficou.

executor.py  
Recebe comandos do commands.json e executa conforme o tipo: shortcut, folder, app, shell ou internal.

commands.json  
Lista dos comandos visíveis no app.

actions/  
Pasta reservada para futuras ações organizadas por categoria.

---

## Tipos de comando

shortcut  
Executa um Atalho do macOS.

folder  
Abre uma pasta.

app  
Abre um aplicativo.

shell  
Executa um comando shell.

internal  
Executa uma ação interna do próprio M87 TERM, como reload.

---

## Exemplo de comando

```json
{
    "code": "AD",
    "label": "Abrir Downloads",
    "type": "folder",
    "value": "~/Downloads"
}


---
# CHANGELOG

## ✅ Concluído

### Interface
- Terminal minimalista em PySide6
- Janela sem moldura
- Redimensionamento da janela
- Posição e tamanho persistentes
- Layout responsivo (1 ou 2 colunas)
- Hover apenas sobre o texto dos comandos

### Barra de status
- Dia da semana
- Data
- Hora
- Temperatura (Porto)
- Bateria
- RAM
- CPU

### Sistema de comandos
- Carregamento via commands.json
- Busca inteligente priorizando código
- Sugestões automáticas
- Navegação por teclado (↑ ↓ Enter)

### Comandos
- BM
- MIN
- KILL
- RE

### Contexto de PDF
- Drag & Drop
- PDF ativo
- Nome do PDF exibido
- Sugestões contextuais
- ESC libera o contexto
- Base preparada para múltiplos tipos de arquivos

### Projeto
- Repositório no GitHub
- Sincronização entre MacBook e Mac Studio
- Estrutura preparada para evolução por contexto

---

## 💡 Ideias

### PDF
- INFO
- CURVAS
- REDUZIR
- RENOMEAR
- Comparar PDFs
- OCR

### Imagem
- OCR
- QR Code
- EAN-13
- Conversão de formatos

### Pasta
- Criar estrutura
- ZIP
- Renomear
- Abrir cliente

### Illustrator
- Curvas
- Gerar PDF
- Limpeza geral
- Relatório de imagens

### Utilidades
- Histórico da área de transferência
- Histórico de clientes
- Histórico de PDFs
- Histórico de pastas
- Pesquisa rápida de arquivos
- Snippets
- Calculadora integrada

### Pipelines
- Saída para gráfica
- Conferência
- Cliente

### IA
- Comandos em linguagem natural
- Sugestão automática de ações
- Assistente integrado

### Futuro
- Contexto para imagens
- Contexto para pastas
- Contexto para Illustrator
- Contexto para InDesign
- Contexto para ZIP
- Contexto para múltiplos arquivos
- Macros
- Plugins