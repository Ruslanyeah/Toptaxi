# autopush.ps1
cd "C:\Users\user\Downloads\toptaxi"

# Добавляем все изменения
git add .

# Дата и время для коммита
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Коммит
git commit -m "Auto backup $timestamp"

# Определяем текущую ветку
$branch = git rev-parse --abbrev-ref HEAD

# Пушим на GitHub
git push origin $branch