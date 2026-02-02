# Usa uma imagem oficial do PHP com Apache
FROM php:8.2-apache

# 1. Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    g++ \
    cmake \
    make \
    zip \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 2. Definir diretório de trabalho
WORKDIR /var/www/html

# 3. Copiar os arquivos do projeto
COPY . .

# 4. Criar pastas necessárias
RUN mkdir -p uploads temp exports

# 5. Compilar o núcleo C++ (ooz)
WORKDIR /var/www/html/ooz_src

# --- CORREÇÃO AQUI ---
# Adicionamos -mavx -msse4.1 -mpclmul para ativar as instruções de CPU necessárias
# Adicionamos -fpermissive para transformar alguns erros de tipos antigos em avisos
RUN g++ -o ../ooz_cli *.cpp -O3 -lpthread -I. -mavx -msse4.1 -mpclmul -std=c++17 -fpermissive

# 6. Voltar para a raiz e ajustar permissões
WORKDIR /var/www/html

RUN chown -R www-data:www-data /var/www/html \
    && chmod -R 755 /var/www/html \
    && chmod +x ooz_cli \
    && chmod 777 uploads temp exports

# 7. Configuração do PHP/Apache
RUN echo "upload_max_filesize = 500M" > /usr/local/etc/php/conf.d/uploads.ini \
    && echo "post_max_size = 500M" >> /usr/local/etc/php/conf.d/uploads.ini \
    && echo "memory_limit = 512M" >> /usr/local/etc/php/conf.d/uploads.ini

RUN a2enmod rewrite

# 8. Expõe a porta 80
EXPOSE 80
