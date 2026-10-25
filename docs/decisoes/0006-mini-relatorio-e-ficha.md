# ADR 0006 — Mini-relatório em PDF e Ficha do Prospect (Fase 1, Tarefa 5)

**Data:** 25/10/2026 · **Status:** aceita

## Contexto
O §8.3 define o "presente" para o prospect: uma página A4 em PDF e uma versão web, com:
1. nota e comparação com a média do setor;
2. os 3 achados com print anotado;
3. quem é afetado;
4. três ações recomendadas, pelo menos uma gratuita;
5. nota metodológica.

O §12.1 (tela 3) pede a Ficha do Prospect. Tudo segue WCAG 2.2 AA (§2.8), e o §21.3 exige que o relatório
passe no axe sem erros críticos.

## Decisões
1. **Identidade visual:** a marca "Sinal Link" do Bloom.
   - Roxo `#5A1B8B`, magenta `#C2188A`, azul-escuro `#1E1E3C` e cinza `#F4F4F4`, em `templates/relatorio/marca.css`.
   - **DM Sans** (licença OFL, pacote `@fontsource/dm-sans` 5.3.0, conferido pelo hash) e o logotipo em PNG,
     ambos em `templates/relatorio/marca/` e embutidos no documento.
2. **Um único HTML para as duas versões:**
   - O modelo Jinja2 `templates/relatorio/relatorio.html` gera a versão web e o PDF.
   - Imagens e fontes vão embutidas em data URI, então a versão web é um arquivo autossuficiente.
   - O PDF sai pelo WeasyPrint 66 como **PDF/UA-1, com tags**: idioma pt-BR, título nos metadados, texto
     alternativo em cada imagem e ordem de leitura do HTML.
   - Testes garantem 1 página, as tags, o idioma, o título e a fonte embutida. A versão web passa no
     **axe sem violações** em 1280 px e em 360 px.
3. **Print anotado sem editar a imagem:**
   - O Auditor técnico passa a guardar a posição na tela do primeiro exemplo de cada problema, em `caixa`, no
     resultado do axe.
   - O relatório e a ficha desenham uma caixa numerada por cima do print, com HTML e CSS.
   - O print tem proporção fixa de 1366 × 768, a mesma da tela do Auditor, para a caixa ficar no lugar e a
     página não estourar.
   - As auditorias anteriores a esta tarefa não têm posições; o print aparece sem caixa e o texto
     alternativo não fala em destaque.
4. **Ações recomendadas por tabela** (`packages/knowledge/acoes-recomendadas.json`), revisada por humanos
   como a do plugin, sem IA:
   - a 1ª é sempre gratuita, algo que a equipe do site faz sozinha (§8.3);
   - a 2ª ataca o problema mais grave;
   - a 3ª é da Sinal Link: a camada de tecnologia assistiva quando o plugin ajuda em algo, ou a avaliação
     manual. O texto sempre diz que o plugin "não substitui a correção do site" (§2.2).
5. **Média do setor:** média da última nota analisada de cada outra empresa do mesmo setor, só a partir de
   **5 sites**. Abaixo disso o relatório diz que ainda não há base para comparar, em vez de mostrar uma
   média enganosa.
6. **Honestidade no documento final:** o HTML completo passa pelo mesmo filtro de frases proibidas da
   Tarefa 4 antes de virar PDF.
7. **Geração e guarda:**
   - O relatório é gerado sem IA, ao fim da análise. Uma falha vira o evento `relatorio_falhou` e não
     desfaz a análise.
   - O PDF e o HTML ficam no MinIO, em `relatorios/<empresa>/<auditoria>.pdf` e `.html`, sem coluna nova.
   - Quem já estava analisado ganha o relatório com `python -m slp_workers.cli relatorios --faltantes`
     (`--listar` para ver antes).
8. **API e Ficha:**
   - `GET /empresas/{id}/ficha`, `/relatorio.pdf`, `/relatorio` e `/prints/{n}`, todas com login.
   - Os endereços `s3://` nunca saem pela API; os prints são servidos pelo índice.
   - A ficha (`/empresas/[id]`) mostra o dossiê completo com as fontes, a auditoria com as evidências
     anotadas, a linha do tempo e os botões "Baixar relatório (PDF)" e "Ver versão web".
   - Os botões de outras fases (assumir conversa, proposta, reauditar) ficam fora.
9. **Imagem do worker:** ganha Pango e HarfBuzz para o WeasyPrint. O `worker-audit` não gera PDF.

## Consequências
- A versão pública do relatório, que o prospect acessa, é o microsite da Fase 5. Por enquanto o vendedor
  baixa o PDF na ficha.
- Reauditar para ter prints anotados das empresas antigas fica para uma tarefa futura.
- Com isso fecham as entregas da Fase 1 (§19). O critério para avançar (20 auditorias revisadas por Marcos,
  com ≥ 90% de achados corretos) é medido sobre estes relatórios.
