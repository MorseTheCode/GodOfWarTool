FROM php:8.2-apache

RUN apt-get update && apt-get install -y \
    g++ \
    cmake \
    make \
    zip \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/www/html

COPY . .

RUN mkdir -p uploads temp exports

WORKDIR /var/www/html/ooz_src

RUN g++ -o ../ooz_cli *.cpp -O3 -lpthread -I.

WORKDIR /var/www/html

RUN chown -R www-data:www-data /var/www/html \
    && chmod -R 755 /var/www/html \
    && chmod +x ooz_cli \
    && chmod 777 uploads temp exports

RUN echo "upload_max_filesize = 500M" > /usr/local/etc/php/conf.d/uploads.ini \
    && echo "post_max_size = 500M" >> /usr/local/etc/php/conf.d/uploads.ini \
    && echo "memory_limit = 512M" >> /usr/local/etc/php/conf.d/uploads.ini

RUN a2enmod rewrite

EXPOSE 80
