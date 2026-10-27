# Planilhas de exemplo

`lote-exemplo.csv` e `lote-exemplo.xlsx` (mesmo conteúdo) servem para testar o upload em lote pelo painel.
Os domínios são fictícios (`*-exemplo*`): confirmar o lote coloca as empresas na fila, e a pesquisa
termina em "site não pôde ser lido". Use só para conferir leitura, mapeamento, prévia e progresso.

O que cada linha exercita:
- linha 2: completa, com contato e CNPJ válido;
- linha 3: site com `https://www.` (normalizado);
- linha 4: CNPJ com dígito errado e UF inexistente (avisos; a empresa entra);
- linha 5: contato com e-mail pessoal (o e-mail é descartado);
- linha 7: mesmo site da linha 2 (repetida);
- linha 8: só nome, sem site (o Pesquisador procuraria o site);
- linha 9: em branco (ignorada, sem contar);
- linha 10: sem nome e com site ilegível (inválida);
- linha 11: mesmo site da linha 4 (repetida).

`lote-colunas-estranhas.csv` tem cabeçalhos sem significado ("Col A", "Col B", "Col C"). As regras não
reconhecem a coluna da empresa, então o worker chama o Haiku para identificar as colunas (cerca de R$ 0,001).
A prévia mostra "Identificadas pela IA".
