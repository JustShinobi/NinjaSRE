# T057 — as cinco consultas de evidência, contra o staging real

A migração está aplicada em staging desde antes desta sessão. Três das cinco
consultas não dependem de um estado anterior e rodaram; duas dependem, e o
estado anterior não existe mais.

## As três que rodaram

**Cobertura — nenhuma linha sem forma pública**

    select count(*) from incidents;                                    -->  30
    select count(*) from incidents where public_id is null
                                      or public_id = '';               -->   0

**Unicidade — nenhuma repetida por organização**

    select coalesce(sum(n-1),0) from (
      select org_id, public_id, count(*) n from incidents
      group by 1,2 having count(*) > 1) d;                             -->   0

**Concordância — o valor gravado é o que o código deriva**

As trinta linhas foram lidas do banco e cada `public_id` recalculado com
`platform.persistence.ports.incident_store.public_incident_id` a partir do
`incident_id` da mesma linha:

    linhas conferidas: 30
    divergentes:       0

    amostra:  alert:alertmanager:441826f5312375a7aba4528bdb9…
              ->  inc_b3e6fe5bdcb708e9

Esta é a mais forte das cinco: ela não pergunta se a coluna está preenchida,
pergunta se o que está lá é o que o código diria hoje. Um valor gravado por uma
versão anterior da derivação apareceria aqui.

## As duas que não rodaram, e por quê

**Total inalterado contra T002** e **chave interna intacta contra a amostra de
T002** comparam com um retrato tirado antes da migração. A T002 nunca foi
executada e a migração já rodou, então o retrato não existe e não pode ser
reconstruído — ao contrário do log do portão da linha de base, que o git
guardava.

O que se pode dizer sem esticar: a propriedade que cada uma guarda está coberta
por `tests/contract/persistence/test_incident_public_id_migration.py`, que faz
o `upgrade` e o `downgrade` contra PostgreSQL real e afirma contagem de linhas
inalterada e `incident_id` intocado. Isso prova o mecanismo. **Não prova estes
trinta registros**, e é por isso que a tarefa fica aberta em vez de arredondada.
