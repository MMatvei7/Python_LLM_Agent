# Базовый образ с Python 3.12
FROM python:3.12-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Копировать requirements
COPY requirements.txt .

# Установить зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копировать весь проект
COPY code_review.py .
COPY .env .

# Копировать дефолтные PDF файлы в контейнер
COPY default_pdfs/ /app/default_pdfs/

# Создать папку для PDF
RUN mkdir -p pdf_documents

# По умолчанию запускать скрипт
ENTRYPOINT ["python", "code_review.py"]
