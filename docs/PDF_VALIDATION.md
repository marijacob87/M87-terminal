# Validação de PDFs

## Regressão automática

`tests/test_imposition.py` gera PDFs sintéticos e verifica:

- MediaBox, CropBox, TrimBox, BleedBox e ArtBox;
- bleed mínimo e bleed assimétrico;
- incompatibilidade entre páginas;
- montagem normal e rotacionada;
- modos repetir e sequencial;
- dimensões da folha;
- conteúdo vetorial;
- metadados básicos;
- análise de cores e prévia;
- validação geométrica da ferramenta CURVAS.

## Amostras reais necessárias

Para validar fluxos de produção são necessárias cópias anonimizadas de:

1. PDF/X-1a em CMYK com OutputIntent/ICC;
2. PDF/X-4 com transparências;
3. PDF com Pantone ou outra spot color;
4. PDF combinando CMYK e Pantone;
5. PDF com TrimBox, BleedBox e ArtBox diferentes;
6. PDF com bleed assimétrico ou caixas fora da origem `0,0`;
7. PDF com páginas rotacionadas;
8. PDF multipágina de frente e verso;
9. PDF com fontes incorporadas e, se disponível, não incorporadas;
10. PDF que já tenha apresentado falha no RIP, Acrobat ou M87.

Os documentos não devem conter informações confidenciais. Textos, nomes,
imagens e metadados podem ser substituídos, desde que a estrutura técnica seja
preservada.

## Propriedades a comparar

- quantidade e ordem das páginas;
- dimensões e origem de todas as caixas;
- rotação;
- resolução efetiva das imagens;
- fontes;
- espaços de cor;
- separações e tintas spot;
- OutputIntent e perfis ICC;
- transparências;
- metadados;
- conformidade PDF/X declarada;
- resultado visual renderizado.

Uma comparação visual isolada não comprova preservação de pré-impressão.

## Saídas derivadas

IMP e CURVAS preservam o OutputIntent e o perfil ICC incorporado da origem.
Tintas spot e transparências também fazem parte da regressão sintética.

A declaração PDF/X não é copiada automaticamente. Alterações de páginas,
caixas, conteúdo ou fontes podem invalidar a conformidade formal mesmo quando
o perfil de impressão permanece correto. Quando a origem declara PDF/X, o M87
informa que o perfil foi preservado e que a conformidade não foi reconfirmada.
