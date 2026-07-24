# M87 TERMINAL
## Guia Oficial de Desenvolvimento para IA

> LEIA ESTE ARQUIVO ANTES DE ALTERAR QUALQUER CÓDIGO.

Este documento define as regras obrigatórias para qualquer atualização do projeto M87 Terminal.

---

# OBJETIVO

O objetivo é manter um código limpo, modular, rápido e estável.

Toda implementação deve respeitar a arquitetura existente.

Nunca alterar aparência, organização ou comportamento do Terminal sem solicitação explícita.

---

# REGRA Nº 1

Sempre considere que este ZIP é a versão mais recente do projeto.

Nunca utilizar código de versões anteriores.

Toda modificação deve ser feita sobre esta versão.

---

# ENTREGA DAS ATUALIZAÇÕES

NUNCA entregar:

- Projeto completo
- Arquivos separados
- Código em texto

A entrega oficial é sempre:

M87_Update_X.X.X.zip

Exemplo:

M87_Update_2.0.0.zip

---

# CONTEÚDO DO ZIP

O pacote deve conter SOMENTE os arquivos modificados.

Nunca incluir arquivos desnecessários.

Sempre incluir:

update.json

Exemplo:

{
    "name": "M87 Update",
    "version": "2.0.0",
    "description": "Descrição curta",
    "restart": true
}

---

# SISTEMA DE ATUALIZAÇÃO

O Terminal possui atualizador próprio.

O usuário irá apenas:

1. Baixar o ZIP
2. Arrastar para o Terminal
3. Pressionar ENTER

O atualizador deverá:

• criar backup

• extrair

• substituir arquivos

• apagar arquivos temporários

• mover o ZIP para a Lixeira

• reiniciar automaticamente

---

# BACKUP

Sempre manter apenas:

backup/
    ultimo_backup.zip

Nunca criar vários backups.

O backup deve conter somente os arquivos substituídos.

---

# ARQUITETURA

Sempre reutilizar código existente.

Evitar duplicações.

Criar novos módulos sempre que fizer sentido.

Funções pequenas.

Responsabilidade única.

---

# NOMES

Sempre utilizar português.

Exemplos:

abrir_pdf()

limpar_lixeira()

atualizar_terminal()

Nunca misturar português e inglês sem necessidade.

Comentários também em português.

---

# PADRÃO VISUAL

Não alterar:

• fonte

• cores

• tamanhos

• alinhamentos

• espaçamentos

• gradientes

• aparência

sem autorização.

---

# JANELAS

A parte superior do Terminal é fixa.

A janela cresce somente para baixo.

Nunca comprimir:

• barra superior

• linha de status

• lista de comandos

---

# PERFORMANCE

Sempre procurar:

• menos imports

• menos código duplicado

• menos timers

• menos consultas repetidas

• menos objetos em memória

Sempre que possível:

modularizar.

---

# LIMPEZA

Sempre remover:

código morto

funções sem uso

imports sem uso

arquivos temporários

__pycache__

comentários antigos

TODO esquecidos

---

# COMPATIBILIDADE

Toda atualização deve preservar:

todos os comandos

todas as ferramentas

todos os atalhos

todas as funcionalidades existentes.

Nunca remover algo sem solicitação.

---

# NOVAS FUNCIONALIDADES

Sempre tentar integrar ao sistema existente.

Não criar soluções paralelas.

Exemplo:

Existe um Drag & Drop.

Novas extensões devem utilizar o mesmo Drag & Drop.

---

# RESPOSTA ESPERADA

Quando solicitado:

"Faça a atualização"

A resposta deve gerar diretamente:

M87_Update_X.X.X.zip

Nunca retornar projeto completo.

---

# FILOSOFIA DO M87

O M87 deve parecer um software profissional.

Poucos cliques.

Máxima automação.

Interface limpa.

Visual consistente.

Tudo deve parecer parte do próprio Terminal.

Sempre que existir um processo repetitivo, procurar automatizá-lo.

---

# ANTES DE FINALIZAR

Verificar:

✓ atualização automática funcionando

✓ backup funcionando

✓ reinício funcionando

✓ sem código duplicado

✓ sem funções mortas

✓ sem alterar layout

✓ sem quebrar funcionalidades

✓ código organizado

Somente então gerar o pacote de atualização.


# CONTEXTO DO PROJETO

Este projeto está em desenvolvimento contínuo.

Sempre que receber um ZIP contendo este arquivo:

- considere este ZIP como a versão oficial do projeto;
- utilize este guia como regra principal de desenvolvimento;
- faça todas as alterações sobre essa versão;
- entregue apenas um pacote de atualização compatível com o sistema de atualização automática do M87.

Caso exista conflito entre uma solicitação do usuário e este documento, prevalece a solicitação do usuário.
