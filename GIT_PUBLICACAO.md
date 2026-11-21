# Sincronização do 2DTruss com o GitHub

O remoto **origin** aponta para o [repositório do 2DTruss](https://github.com/PFelipe23/2DTruss). Use uma branch de trabalho para preparar os commits e abra um pull request para **main**.

1. Na raiz do repositório, execute `git status -sb` para conferir a branch e `git fetch origin` para atualizar as referências do GitHub.
2. Use `git log --oneline origin/main..HEAD` para revisar os commits que irão no pull request. Execute `python -m pytest -q -rs tests` com as dependências de `requirements-test.txt`.
3. Na primeira publicação da branch atual, execute `git push -u origin HEAD`. Nos envios seguintes, use `git push`. Abra o pull request com **main** como destino.
4. Se o GitHub indicar divergência, consulte os commits de ambos os lados antes de integrar alterações.

Versione o código, os testes, os modelos de exemplo e as imagens usadas na documentação. Os executáveis e intermediários de build ficam em `dist/` e `build/`. Salve PDFs, exportações e prévias temporárias em `output/`. Essas três pastas já estão ignoradas no Git.

## Registro da publicação inicial do 2DTruss v0.1

O [repositório oficial](https://github.com/PFelipe23/2DTruss) já está publicado com a licença MIT. O procedimento abaixo documenta a preparação do primeiro envio e fica como registro histórico.

1. No GitHub, crie um **repositório vazio e privado** com nome `2DTruss`, na conta `PFelipe23`. Não inicialize com README ou licença.
2. Extraia o ZIP **com a pasta oculta `.git`** e abra o terminal na raiz do projeto.
3. Execute:

```bash
git remote add origin https://github.com/PFelipe23/2DTruss.git
git push -u origin main
git push origin v0.1
```

Se o remoto não estiver vazio ou o nome já estiver ocupado, pare e revise o histórico antes de tentar novamente. Não use `--force`.
