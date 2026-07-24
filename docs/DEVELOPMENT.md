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
git diff --check
```

Além da regressão automática, alterações de interface precisam de uma
verificação manual no macOS.

## Fluxo recomendado

1. consultar `AGENTS.md`;
2. verificar alterações locais com `git status`;
3. procurar componentes e funções existentes;
4. fazer a menor alteração capaz de resolver o problema;
5. adicionar ou atualizar testes;
6. executar a validação obrigatória;
7. testar manualmente apenas o fluxo afetado;
8. revisar o diff antes de criar o pacote.

## Regras de segurança

- não sobrescrever PDFs sem confirmação;
- preferir “Salvar Como”;
- não apagar arquivos automaticamente;
- manter processamento pesado fora da thread gráfica;
- preservar as caixas e características gráficas do PDF;
- não alterar aparência ou atalhos sem autorização;
- não modificar o formato do atualizador.

## Pacotes de atualização

As regras completas estão em `000_LEIA_PRIMEIRO_M87.md`.

O pacote deve conter somente:

- `update.json`;
- arquivos efetivamente modificados, nos caminhos relativos do projeto.

Exemplo:

```json
{
  "name": "M87 Update",
  "version": "2.0.0",
  "description": "Descrição curta",
  "restart": true,
  "files": [
    "core/exemplo.py",
    "ui/exemplo_dialog.py"
  ]
}
```
