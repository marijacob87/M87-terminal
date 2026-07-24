# M87 Terminal

Aplicação desktop para macOS que centraliza automações de produção gráfica,
pré-impressão e tarefas recorrentes numa interface compacta inspirada em
terminal.

O M87 permite executar ações por códigos curtos, clicar na lista de comandos
e arrastar PDFs diretamente para a janela.

## Funcionalidades principais

- abertura de aplicativos, pastas, atalhos e unidades de rede;
- rotina de início e encerramento do expediente;
- pesquisa de clientes, aplicativos e pastas recentes;
- análise, renomeação, intercalação e conversão de PDFs em curvas;
- imposição de PDFs em modo individual ou lote;
- cálculo de montagem;
- geração e leitura de QR Code e EAN-13;
- atualização local por pacote ZIP com backup e rollback.

## Requisitos

- macOS;
- Python 3.12;
- Ghostscript para a ferramenta CURVAS;
- fonte JetBrains Mono;
- dependências listadas em `requirements.txt`.

## Instalação

```bash
python3.12 -m venv "$HOME/.venvs/m87_terminal"
"$HOME/.venvs/m87_terminal/bin/python" -m pip install -r requirements.txt
```

Para iniciar:

```bash
./run_m87.sh
```

O interpretador também pode ser definido explicitamente:

```bash
M87_PYTHON="/caminho/para/python" ./run_m87.sh
```

Na primeira utilização, o macOS poderá solicitar permissões para controlar o
Finder, System Events e outros aplicativos usados pelas automações.

## Desenvolvimento

Execute a regressão antes de entregar alterações:

```bash
"$HOME/.venvs/m87_terminal/bin/python" -m unittest discover -v
"$HOME/.venvs/m87_terminal/bin/python" -m compileall -q main.py core ui scripts tests
```

As regras obrigatórias do projeto estão em [AGENTS.md](AGENTS.md). O formato
dos pacotes de atualização está documentado em
[000_LEIA_PRIMEIRO_M87.md](000_LEIA_PRIMEIRO_M87.md).

## Estrutura

```text
assets/     ícones e recursos visuais
core/       regras de negócio, automações e processamento
scripts/    processos externos independentes
tests/      regressão automatizada
ui/         janelas, widgets e controladores da interface
```

Documentação adicional:

- [Arquitetura](docs/ARCHITECTURE.md)
- [Desenvolvimento](docs/DEVELOPMENT.md)
- [Validação de PDFs](docs/PDF_VALIDATION.md)
- [Roadmap](docs/ROADMAP.md)
- [Histórico de alterações](CHANGELOG.md)
