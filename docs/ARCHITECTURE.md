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
- `pdf_context.py`: drag and drop e ações do PDF ativo;
- `tools_dialog.py`: janela compartilhada entre IMP, GEO, MON e BAR;
- `widgets.py`: componentes reutilizáveis.

Operações lentas devem usar `QThread`, `QProcess` ou worker equivalente.

### `core/`

Contém regras de negócio e integrações:

- `executor.py`: despacho dos tipos definidos em `commands.json`;
- `input_handler.py`: interpretação do prompt;
- `imposition.py`: inspeção, cálculo e exportação de imposições;
- `pdf_info.py`: análise estrutural de PDFs;
- `update_manager.py`: validação, backup, instalação e rollback;
- `system_actions.py`: ações de sessão e limpeza;
- `code_tools.py`: QR Code e EAN-13.

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

## Atualizações

O pacote contém `update.json` e apenas os arquivos modificados. O instalador:

1. valida manifesto e caminhos;
2. cria `backup/ultimo_backup.zip`;
3. extrai para staging;
4. preserva os arquivos anteriores para rollback;
5. substitui cada destino atomicamente;
6. restaura tudo se qualquer substituição falhar;
7. move o pacote instalado para a Lixeira.

O formato de `update.json` não deve ser alterado.
