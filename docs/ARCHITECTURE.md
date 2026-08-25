# Arquitetura

## Visão geral

O M87 Terminal usa Python, PySide6 e integrações nativas do macOS por PyObjC,
AppleScript e utilitários do sistema.

O ponto de entrada é `main.py`. Ele configura o Qt e cria `ui.ui.M87Term`.
A janela principal combina controladores por mixins, mantendo construção
visual, comportamento, comandos, status e contexto de PDF separados.

## Camadas

### `ui/`

Responsável apenas pela apresentação e interação:

- `ui.py`: composição da janela principal;
- `window_ui.py`: construção dos widgets da janela;
- `window_behavior.py`: movimento, tamanho e persistência;
- `command_controller.py`: comandos e ferramentas;
- `command_workflows.py`: rotinas assíncronas iniciadas pelos comandos;
- `pdf_context.py`: drag and drop e ações do PDF ativo;
- `tools_dialog.py`: janela compartilhada entre ORG, GEO, IMP, MON e BAR;
- `tools_components.py`: barra de abas e camada compartilhada de drop;
- `imposition_preview.py`: renderização e navegação da prévia de imposição;
- `geometry_controls.py`: seletor de âncora da geometria;
- `geometry_preview.py`: renderização e navegação da prévia geométrica;
- `geometry_workers.py`: execução assíncrona das alterações geométricas;
- `design_tokens.py`: fonte única de cores, dimensões e espaçamentos;
- `tool_design.py`: componentes e estilos compartilhados pelas ferramentas;
- `organize_pages_widget.py`: interface de organização de páginas;
- `widgets.py`: componentes reutilizáveis.

Operações lentas devem usar `QThread`, `QProcess` ou worker equivalente.

### `core/`

Contém regras de negócio e integrações:

- `executor.py`: despacho dos tipos definidos em `commands.json`;
- `input_handler.py`: interpretação do prompt;
- `imposition.py`: inspeção, cálculo e exportação de imposições;
- `pdf_info.py`: análise estrutural de PDFs;
- `system_actions.py`: ações de sessão e limpeza;
- `code_tools.py`: QR Code e EAN-13.
- `konica_spool.py`: envio de PDFs ao Hot Folder/Hold da Konica;
- `project_metadata.py`: leitura de referência, histórico Git e informações do sistema;

Funções puras devem permanecer independentes do Qt sempre que possível.

### `scripts/`

Processos que podem ser executados separadamente:

- `convert_pdf_to_curves.py`: conversão via Ghostscript;
- `intercalar_pdf.py`: intercalação de frente e verso.

### `tests/`

Testes unitários e de integração com arquivos temporários. PDFs sintéticos são
gerados durante a execução e nunca utilizam documentos do usuário.

## Configuração e estado

- `commands.json`: comandos exibidos e executados pelo terminal;
- `reference.json`: conteúdo da referência integrada;
- `state.json`: posição e tamanho persistentes da janela;
- `core/config.py`: constantes e caminhos resolvidos pela raiz do projeto.

## Sistema visual

As cinco ferramentas são superfícies da mesma `ToolsDialog`. Parâmetros
globais ficam em `ui/design_tokens.py`; widgets e QSS compartilhados ficam em
`ui/tool_design.py`. A especificação completa e o checklist de revisão estão
em `docs/VISUAL_SYSTEM.md`.

Não é permitido criar uma versão local de um componente que já exista nesse
módulo. Exceções visuais de janelas especializadas devem ser deliberadas e não
podem alterar os estados ou medidas das ferramentas compartilhadas.
