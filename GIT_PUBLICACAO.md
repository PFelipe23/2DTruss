# Publicar 2DTruss v0.1 no GitHub

O repositório Git local contém branch `main` e tag anotada **v0.1**. Não existe um repositório remoto publicado automaticamente.

1. No GitHub, crie um **repositório vazio e privado** com nome `2DTruss`, na conta `PFelipe23`. Não inicialize com README ou licença.
2. Extraia o ZIP **com a pasta oculta `.git`** e abra o terminal na raiz do projeto.
3. Execute:

```bash
git remote add origin https://github.com/PFelipe23/2DTruss.git
git push -u origin main
git push origin v0.1
```

Se o remoto não estiver vazio ou o nome já estiver ocupado, pare e revise o histórico antes de tentar novamente. Não use `--force`.
