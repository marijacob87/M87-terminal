# Histórico de alterações

## 2.0.0 — 24/07/2026

### Estabilidade

- caminhos de configuração independentes da pasta de lançamento;
- gravação atômica do estado da janela;
- consultas de status e Finder fora da thread gráfica;
- rollback automático de atualizações incompletas;
- dependências nativas do macOS documentadas.

### Qualidade

- regressão automatizada para lógica principal;
- testes sintéticos de caixas, análise e imposição de PDFs;
- validação real da conversão CURVAS com Ghostscript;
- preservação de metadados básicos na imposição;
- preservação atômica de OutputIntent e perfis ICC no IMP e CURVAS;
- aviso quando uma origem PDF/X gera uma saída sem conformidade reconfirmada;
- documentação separada por finalidade.

## Histórico funcional

- terminal compacto em PySide6;
- sistema de comandos e sugestões;
- contexto de PDF por drag and drop;
- ferramentas IMP, GEO, MON e BAR;
- análise, renomeação, intercalação e conversão em curvas;
- atualização local por pacote ZIP.
