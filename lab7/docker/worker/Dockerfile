FROM php:8.3-alpine

RUN docker-php-ext-install pdo_mysql

WORKDIR /var/www/html

CMD ["php", "worker.php"]