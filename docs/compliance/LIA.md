# Relatório de Legítimo Interesse (LIA) — rascunho

> Modelo inicial para a CONSTITUICAO §15.1. **Deve ser revisado e validado por advogado** antes do início
> dos envios (Fase 3).

## 1. Finalidade
Contato comercial B2B com profissionais, em seu papel corporativo, de organizações que podem se beneficiar
de soluções de acessibilidade digital, acompanhado de diagnóstico gratuito do site público da organização.

## 2. Necessidade
- Dados coletados: nome, cargo, e-mail corporativo, empresa, área de atuação, link público de perfil profissional.
- Não coletamos dados sensíveis nem dados pessoais fora do contexto profissional.
- A auditoria analisa apenas páginas públicas do site da organização.

## 3. Balanceamento
- Expectativa razoável: profissionais de TI, RH, D&I, Marketing, ESG e Compliance recebem contatos relacionados à sua função.
- Benefício ao titular: diagnóstico concreto e gratuito, útil mesmo sem contratação.
- Salvaguardas: opt-out em um clique, honrado imediatamente e para sempre; limite de frequência;
  identificação clara do remetente e do motivo do contato; atendimento a direitos do titular em até 15 dias;
  anonimização após 18 meses sem interação.

## 4. Fontes dos dados
Apollo.io (base B2B), site público da organização, notícias públicas. Sem raspagem de redes sociais.

Decisores (Mapeador, ADR 0009):
- Nome e cargo vêm da busca de pessoas do Apollo ou, quando ela não cobre a área, de fontes públicas
  encontradas pela busca web (site oficial da organização, comunicados, relatórios, imprensa). A URL da fonte
  fica guardada com o contato.
- O LinkedIn nunca é fonte nem é lido: um link de perfil só é guardado quando aparece nos próprios resultados
  da busca ou no registro do Apollo.
- O e-mail é sempre o profissional, no domínio da organização, obtido no Apollo e validado (MX e verificação).
  Não pedimos e-mail pessoal nem telefone.
- Quando o Apollo não está disponível (ADR 0012), o e-mail profissional é **inferido** a partir do nome e do
  padrão do domínio da organização (ex.: nome.sobrenome@) e só é aceito se um verificador (Apify) confirmar por
  SMTP que a caixa existe e que o domínio não aceita qualquer endereço (catch-all). E-mails de função, pessoais e
  descartáveis são recusados; os endereços testados e não confirmados não são guardados.

## 5. Encarregado (DPO) e contato
_Preencher: nome e e-mail do encarregado pelo tratamento de dados da Sinal Link._
