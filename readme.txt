Visual Studio Code终端运行：
cd /c/surveyingmaster
# 1. 本地提交（master 改名为 main，和远程对齐）
git branch -M main
git add -A
git commit -m "数测通 v3.0.1 发布版"

# 2. 强制推送覆盖远程旧历史
git push --force origin main