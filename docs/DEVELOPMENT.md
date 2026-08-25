# Desenvolvimento

## Ambiente

O ambiente padrão fica em:

```text
$HOME/.venvs/m87_terminal
```

Criação e instalação:

```bash
python3.12 -m venv "$HOME/.venvs/m87_terminal"
"$HOME/.venvs/m87_terminal/bin/python" -m pip install -r requirements.txt
```

## Validação obrigatória

```bash
"$HOME/.venvs/m87_terminal/bin/python" -m unittest discover -v
"$HOME/.venvs/m87_terminal/bin/python" -m compileall -q main.py core ui scripts tests
bash -n run_m87.sh
bash -n scripts/build_macos_app.sh
git diff --check
```

## Aplicativo nativo do macOS

O bundle de desenvolvimento mantém o código e os recursos ligados à pasta do
projeto:

```bash
./scripts/build_macos_app.sh
open "dist/M87 Terminal.app"
```

O nome nativo é definido em `scripts/macos_Info.plist` por `CFBundleName` e
`CFBundleDisplayName`. O launcher incorpora o mesmo Python do ambiente virtual
no processo nativo, sem duplicar o código do projeto. O `run_m87.sh` permanece
disponível para diagnóstico e desenvolvimento pelo terminal.

Além da regressão automática, alterações de interface precisam de uma
verificação manual no macOS. Use `docs/VISUAL_SYSTEM.md` como checklist.

## Fluxo recomendado

1. consultar `AGENTS.md`;
2. verificar alterações locais com `git status`;
3. procurar componentes e funções existentes;
4. fazer a menor alteração capaz de resolver o problema;
5. para interface, alterar primeiro `ui/design_tokens.py` ou o componente
   compartilhado em `ui/tool_design.py`;
6. adicionar ou atualizar testes;
7. executar a validação obrigatória;
8. testar manualmente o fluxo afetado com e sem PDF;
9. revisar o diff antes de publicar as alterações.

Ao separar módulos, preserve os caminhos públicos usados por outras abas e
extraia responsabilidades completas. Prévias, workers e componentes de janela
podem viver em módulos próprios; regras independentes de Qt permanecem em
`core/`.

## Regras de segurança

- não sobrescrever PDFs sem confirmação;
- preferir “Salvar Como”;
- não apagar arquivos automaticamente;
- manter processamento pesado fora da thread gráfica;
- preservar as caixas e características gráficas do PDF;
- não alterar aparência ou atalhos sem autorização.
