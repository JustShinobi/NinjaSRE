# Controle — 020 Resources

Reconciliado por confronto em 2026-08-13. Ver
`specs_v4/020-resources/relatorio-confronto.md` para as evidências,
arquivo:linha, e os gates rodados. Cinco das sete linhas abaixo marcadas NÃO
INICIADO estavam erradas: três já estavam feitas por completo antes deste
confronto (itens 3, 4, 7) e duas estavam parcialmente feitas (5, 8). Só os
itens 2 e 6 estavam de fato intocados.

| Item | Estado | Detalhe |
|---|---|---|
| 1. Clicar parece não fazer nada | **FEITO** (`bf5f055`) | Confirmado no confronto — sem regressão. Painel de detalhe acima da tabela, nomeado, com volta preservando filtros. Sem client JS. Coberto por `resource-detail.test.tsx`. |
| 2. Detalhe com chave de outro recurso (`lxc/HAL9000/unknown/111`) | **FEITO** (confronto 2026-08-13) | Não era bug do console — a chave vinha malformada do backend. `_resolve_up` em `platform/estate/signal_map.py` usava `resource.native_id` (identidade interna de reconciliação do Proxmox, que embute o marcador "unknown" quando falta a data de criação do guest) como se fosse o "nome" do recurso. Corrigido para resolver pela mesma função `_key_for` que todo outro vínculo por nome usa. Teste novo em `test_signal_map.py`, confirmado vermelho antes. |
| 3. Coluna morta Utilisation | **FEITO** (já estava, antes deste confronto) | O controle dizia NÃO INICIADO; a leitura do código mostrou a coluna e o cabeçalho já condicionados a haver alguma leitura na vista atual. Coberto por `resources.test.tsx`. Nenhuma mudança necessária. |
| 4. Vocabulários de saúde que não fecham | **FEITO** (já estava, antes deste confronto) | O controle dizia NÃO INICIADO ("Onda 4" pendente); header, badges, filtro e dashboard já liam a mesma repartição `by_health`/`problems`, com o card do dashboard nomeando explicitamente a união ("Degraded and unhealthy"). Nenhuma mudança necessária. |
| 5. "(not in the inventory)" no nome | **FEITO** (confronto 2026-08-13) | Parcial antes do confronto: já tinha saído do nome e virado coluna própria, mas era texto mudo sem explicação. Adicionado tooltip (`hint` em `Cell`) explicando o que é o inventário declarado e o que fazer. |
| 6. "Unplaced"/"Ungraded" | **FEITO** (confronto 2026-08-13) | Confirmado intocado pelo controle. Adicionado tooltip + link para `/configuration` (onde zona/criticidade são declaradas), só quando o valor é o marcador — um valor já declarado não ganha link. |
| 7. Sem busca por nome | **FEITO** (já estava, antes deste confronto) | O controle dizia NÃO INICIADO; o filtro `q` já existia, com formulário GET preservando os demais filtros. Nenhuma mudança necessária. A busca global (spec 001) continua fora do escopo desta tela. |
| 8. "Worst first" órfão / sort leak | **FEITO** (confronto 2026-08-13) | O vazamento do cabeçalho ("SORT, SMALLEST FIRST") já estava corrigido em todo o app pelo componente compartilhado `rows.tsx` (spec 012) — nenhuma ocorrência restante encontrada. O rótulo "Worst first" continuava órfão; adicionado tooltip explicando que é a ordem padrão e que um cabeçalho de coluna muda isso. |
