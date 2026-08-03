# Integração Controle Konica

1. Abra a planilha **Controle Konica**.
2. Acesse **Extensões → Apps Script**.
3. Substitua o conteúdo de `Code.gs` pelo arquivo desta pasta.
4. Troque `SUBSTITUA_POR_UMA_CHAVE_LONGA_E_SECRETA` por uma chave privada.
5. Clique em **Implantar → Nova implantação → Aplicativo da Web**.
6. Selecione **Executar como: você** e acesso **Qualquer pessoa**.
7. Autorize e copie a URL terminada em `/exec`.
8. No primeiro envio do M87, cole a URL e a mesma chave na confirmação.

O script só escreve nas colunas A, B, C, F e G. As fórmulas e a formatação
existentes permanecem intactas.
