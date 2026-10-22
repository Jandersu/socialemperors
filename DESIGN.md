---
name: Social Empires — Rivais e Tesouro
description: Registro do portal azul existente e das telas Rivais e Tesouro implementadas.
colors:
  primary: "#3b5998"
  page: "#f6f7fa"
  surface: "#ffffff"
  separator: "#e3e7ee"
  text: "#202b3d"
  muted: "#626d7d"
rounded:
  surface: "12px"
---

# Design do portal, Rivais e Tesouro

## Overview

O portal mantém sua identidade azul, o logo e a navegação existentes. O usuário pediu uma apresentação minimalista e moderna, com apenas o texto necessário, **para Rivais e Tesouro**. Este documento registra o resultado executado; não autoriza redesenhar outras rotas. Os tokens acima descrevem essas duas telas.

O contexto do produto está em [PRODUCT.md](PRODUCT.md). Rivais tem seu [brief](.impeccable/surfaces/templates-rivals-html.md), [template](templates/rivals.html), [CSS](templates/css/rivals.css) e [JavaScript](templates/js/rivals.js); Tesouro tem seu [brief](.impeccable/surfaces/templates-treasury-html.md), [template](templates/treasury.html), [CSS](templates/css/treasury.css) e [JavaScript](templates/js/treasury.js). O [portal-shell.css](templates/css/portal-shell.css) compartilha o cabeçalho, navegação, tipografia-base e fundo das duas telas. Essa extração manteve os valores visuais de Rivais, cujas variáveis locais agora referenciam as compartilhadas.

As revisões independentes terminaram com **ship**, sem pendências. Rivais teve 93 verificações de navegador e quatro achados resolvidos. Tesouro teve 96 verificações iniciais e 31 de confirmação focada, sem erros de JavaScript; o único achado foi resolvido com o link Atualizar junto ao prazo de resgate. Os 103 testes automatizados passaram; após esse ajuste, os nove testes de gestão passaram novamente. Os cenários usaram dados isolados em `/tmp`; capturas ficam fora do Git. A aparência de Rivais foi preservada em desktop e celular.

## Colors

O azul existente destaca ações e a aba selecionada. Rivais e Tesouro usam fundo neutro claro, superfícies brancas, separadores finos, texto escuro e texto secundário atenuado, conforme os tokens. Os estados de resultado mantêm suas cores semânticas implementadas.

## Typography

As duas telas usam `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. O título principal mede 32 px e passa a 29 px até 540 px. Em Rivais, o nome da própria vila passa de 21 a 20 px; o conteúdo de tarefa usa principalmente 13–14 px. No Tesouro, o saldo passa de 26 a 24 px, os títulos das recompensas de 15 a 14 px e seus valores de 20 a 18 px. Números usam algarismos tabulares. Nomes longos podem quebrar linha; valores completos são preservados.

## Layout

A própria vila e a área de trabalho formam as duas superfícies principais. Resumo, força e recursos permanecem antes das abas. No desktop, os rivais ocupam linhas alinhadas; no celular, as informações são empilhadas e o botão Atacar ocupa a largura disponível. Na classificação móvel, as métricas ficam abaixo do nome da vila. Os recursos usam flex com quebra de linha e largura intrínseca, sem apertar ou truncar seus números.

Tesouro tem largura máxima de 960 px e um painel de saldo com linhas de bônus inicial e recompensa diária. No desktop, nome, valor e ação ficam alinhados; no celular, o botão passa para a linha seguinte e ocupa a largura disponível. Histórico e ajuda ficam abaixo do painel.

## Elevation & Depth

As duas telas usam organização plana: fundo, superfícies e separadores definem os grupos. As linhas não são cartões individuais e não recebem sombras decorativas.

## Shapes

As duas superfícies principais de Rivais e o painel de saldo do Tesouro têm raio de 12 px e borda fina neutra. Linhas e separadores internos mantêm a composição de lista.

## Components

As abas **Vilas**, **Classificação** e **Histórico** são aprimoradas progressivamente: aceitam setas, Home e End, mantêm links por fragmento da URL e deixam todos os painéis acessíveis sem JavaScript. O foco permanece visível.

Cada rival reúne identificação, defesa, saque possível e ação. Ataques bloqueados mostram o motivo. Regras breves ficam em um disclosure recolhido; o histórico oferece detalhes do combate. Formulários, CSRF, tokens assinados e autoridade do servidor foram preservados.

No Tesouro, o histórico mostra os três resgates mais recentes e mantém os demais, até o limite existente de 20, em um disclosure nativo. A ajuda também fica recolhida. Recompensas e limite de saldo vêm do servidor. Um resgate que excederia a capacidade fica desabilitado, com o motivo associado por `aria-describedby`. O prazo diário mostra data e hora e um link **Atualizar**, que faz nova consulta por GET; o relógio do navegador não libera o botão.

Os formulários de resgate preservam POST, CSRF e `action` em campo oculto, funcionando sem JavaScript. Quando disponível, o script mostra **Resgatando…** e bloqueia envios repetidos sem perder a ação submetida. Nenhuma recompensa, saldo, regra de intervalo ou condição de pagamento foi alterada.

## Do's and Don'ts

- Manter português do Brasil, dados reais da vila e explicações necessárias para decidir um ataque.
- Preservar o logo e as artes originais; este trabalho não recria o jogo.
- Restringir a nova composição a Rivais e Tesouro; as demais rotas seguem suas implementações atuais.
- Não alterar regras de combate, distribuição de dinheiro ou ausência de pagamentos por motivo visual.
