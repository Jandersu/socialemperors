---
name: Social Empires — Rivais
description: Registro do portal azul existente e da tela Rivais implementada.
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

# Design do portal e de Rivais

## Overview

O portal mantém sua identidade azul, o logo e a navegação existentes. O usuário pediu uma apresentação minimalista e moderna, com apenas o texto necessário, **para a tela Rivais**. Este documento registra o resultado executado; não autoriza redesenhar outras rotas. Os tokens acima descrevem essa tela.

O contexto do produto está em [PRODUCT.md](PRODUCT.md). As decisões e o escopo da superfície estão no [brief de Rivais](.impeccable/surfaces/templates-rivals-html.md); a implementação está no [template](templates/rivals.html), [CSS](templates/css/rivals.css) e [JavaScript](templates/js/rivals.js). A revisão independente terminou com **ship**, com quatro achados resolvidos e nenhuma pendência. A verificação concluída cobriu 93 verificações no navegador, sem erros de JavaScript, larguras de 320 a 1920 px e 103 testes automatizados aprovados. Dados de teste não foram acrescentados à produção.

## Colors

O azul existente destaca ações e a aba selecionada. Rivais usa fundo neutro claro, superfícies brancas, separadores finos, texto escuro e texto secundário atenuado, conforme os tokens. Os estados de resultado mantêm suas cores semânticas implementadas.

## Typography

Rivais usa `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. O título principal mede 32 px e o nome da própria vila, 21 px; até 540 px, passam a 29 e 20 px. O conteúdo de tarefa usa principalmente 13–14 px. Números usam algarismos tabulares. Nomes longos podem quebrar linha; valores completos são preservados.

## Layout

A própria vila e a área de trabalho formam as duas superfícies principais. Resumo, força e recursos permanecem antes das abas. No desktop, os rivais ocupam linhas alinhadas; no celular, as informações são empilhadas e o botão Atacar ocupa a largura disponível. Na classificação móvel, as métricas ficam abaixo do nome da vila. Os recursos usam flex com quebra de linha e largura intrínseca, sem apertar ou truncar seus números.

## Elevation & Depth

Rivais usa organização plana: fundo, superfícies e separadores definem os grupos. As linhas não são cartões individuais e não recebem sombras decorativas.

## Shapes

As duas superfícies principais têm raio de 12 px e borda fina neutra. Linhas e separadores internos mantêm a composição de lista.

## Components

As abas **Vilas**, **Classificação** e **Histórico** são aprimoradas progressivamente: aceitam setas, Home e End, mantêm links por fragmento da URL e deixam todos os painéis acessíveis sem JavaScript. O foco permanece visível.

Cada rival reúne identificação, defesa, saque possível e ação. Ataques bloqueados mostram o motivo. Regras breves ficam em um disclosure recolhido; o histórico oferece detalhes do combate. Formulários, CSRF, tokens assinados e autoridade do servidor foram preservados.

## Do's and Don'ts

- Manter português do Brasil, dados reais da vila e explicações necessárias para decidir um ataque.
- Preservar o logo e as artes originais; este trabalho não recria o jogo.
- Restringir a nova composição a Rivais; as demais rotas seguem suas implementações atuais.
- Não alterar regras de combate, distribuição de dinheiro ou ausência de pagamentos por motivo visual.
