# Arquitetura e decisões

## Caminho de uma operação

As páginas em `sgc.ui` coletam os dados e chamam `Services`. Os serviços verificam a existência e a situação do usuário, sua empresa e o perfil autorizado antes de consultar ou alterar registros. A interface não fornece uma sessão SQLAlchemy ao usuário.

O ator da sessão contém ID do usuário e empresa. A cada operação o serviço consulta a conta no banco; o perfil não é aceito como argumento confiável da tela. Não há cookie persistente para restaurar a autenticação.

Senhas são armazenadas com PBKDF2-HMAC-SHA256, salt aleatório por senha e 600 mil iterações. Não há fallback para texto simples ou SHA256 direto. Cinco tentativas de login malsucedidas bloqueiam a combinação de empresa e usuário por um minuto. Esse mecanismo local não substitui proteção contra abuso distribuído em uma implantação pública.

## Modelo financeiro

```text
empresa
  usuários, clientes, produtos
  vendas -> itens de venda e parcelas
  recebimentos -> destinações em parcelas
  auditoria
```

Cada parcela possui valor contratado e valor recebido, ambos em centavos inteiros. A situação é derivada do saldo e do vencimento. Vendas canceladas ficam registradas e são excluídas dos indicadores.

No crediário, o saldo após a entrada recebe o acréscimo único informado. Exemplo: preço de R$ 100,00, entrada de R$ 20,00 e acréscimo de 10% geram R$ 8,00 de acréscimo e R$ 88,00 parcelados. A entrada de R$ 20,00 também fica registrada como recebimento. Não há cálculo de encargos por atraso.

O saldo é repartido em centavos, com eventuais centavos adicionais nas primeiras parcelas. R$ 100,01 em três parcelas resulta em R$ 33,34, R$ 33,34 e R$ 33,33.

O recebimento primeiro preenche o saldo da parcela selecionada, depois os das parcelas de número posterior da mesma venda. Cada destinação fica registrada em `allocations`. Se o valor superar a soma desses saldos, toda a operação é recusada. Parcelas anteriores à selecionada não são alteradas por esse fluxo.

## Transações e concorrência

Operações de escrita iniciam `BEGIN IMMEDIATE` no SQLite antes de ler estoque ou saldo. Isso serializa as alterações e evita que duas confirmações consumam o mesmo último item ou gravem um saldo baseado na mesma leitura antiga. O tempo limite de espera pelo banco é de 15 segundos.

Vendas e recebimentos possuem chave de operação única por empresa. A repetição da chave com o mesmo conteúdo retorna o registro anterior. Conteúdo divergente ou usuário diferente é recusado. A chave não é reutilizada para reaplicar um pagamento estornado.

O estorno mantém o recebimento e suas destinações, marcando-o como revertido. O saldo é restaurado exatamente pelos valores destinados. Apenas o recebimento mais recente ainda ativo da venda pode ser desfeito, em até cinco minutos. Cobradores desfazem apenas seus próprios recebimentos; administradores podem desfazer os da empresa. Entradas e pagamentos à vista não são estornados por esse fluxo.

Cancelamentos são restritos ao administrador e a vendas sem valores recebidos. Os produtos retornam ao estoque na mesma transação que marca a venda como cancelada. Não há exclusão arbitrária de parcela.

## Backup e armazenamento

A aplicação cria um banco novo em `data/sgc_demo.db`. O diretório é independente da pasta atual e pode ser configurado com `SGC_DATA_DIR`.

O backup usa a API `sqlite3.Connection.backup`, em vez de copiar o arquivo aberto. É uma ferramenta local do operador, pois inclui todas as empresas e os hashes de senha. Não há endpoint nem botão para disponibilizar um backup global a um usuário de uma empresa.

O esquema não implementa migrações. `create_all` cria as tabelas ausentes, mas não converte arquivos antigos nem altera tabelas existentes quando o modelo muda. Esta edição não é uma atualização automática da base legada.

## Interface e comprovante

O Streamlit serve páginas, formulários e gráficos locais. Textos cadastrados são exibidos por componentes nativos; os trechos de HTML usados na identidade visual são estáticos. O comprovante usa escape de texto no ReportLab e contém o valor registrado e as destinações em parcelas. Ele não comprova uma transferência bancária e não tem validade fiscal.

As sessões expiram por inatividade e são encerradas na saída ou troca de senha. Desativação da conta e mudança de perfil são verificadas no acesso seguinte aos serviços. A troca de senha incrementa a versão de autenticação da conta, invalidando também os atores de outras sessões já abertas no próximo acesso aos serviços.

## Diferenças em relação ao projeto original

- Regras separadas do arquivo de interface, com testes independentes do navegador.
- Valores em centavos, em vez de `Float` nos registros financeiros.
- Login unificado, sem senha padrão criada automaticamente ao iniciar.
- Base fictícia explícita e sem importação de clientes, backups ou credenciais legadas.
- Filtro de empresa aplicado às consultas e às alterações de registros.
- Recebimento parcial preserva o saldo; excedentes são distribuídos e auditados.
- Backup consistente e separado do acesso por empresa.
- Firebase administrativo, API FastAPI legada e empacotamento antigo retirados desta demonstração. Não há sincronização em nuvem ou novo executável nesta edição.

## Distribuição de portfólio

Este repositório foi iniciado com um histórico novo, a partir de uma lista permitida de arquivos de código, testes, documentação e imagens fictícias. Ele não contém a pasta Git, bancos, backups ou credenciais do projeto legado.

A edição funciona localmente e não autentica nem faz chamadas a uma conta Firebase. Arquivos de uso são criados em `data/`, ignorado pelo Git. A ferramenta `tools/export_portfolio.py` permite reproduzir a distribuição de fontes.

## Próximos passos para uso compartilhado

- Migrações de esquema e importação revisada dos dados legados.
- Provisionamento de empresas e administradores fora da base de demonstração.
- Recuperação de senha e registro de tentativas de autenticação bem-sucedidas e malsucedidas.
- Regras comerciais completas de descontos, encargos, devoluções e cancelamentos com recebimentos.
- Restauração de backup validada, retenção e criptografia dos arquivos locais.
- Paginação, filtros e medição de desempenho com volumes reais.
