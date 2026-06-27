<?php
require_once 'Database.php';
require_once 'UserService.php';

function appLog(string $message): void {
    error_log('[WEB][' . date('Y-m-d H:i:s') . '] ' . $message);
}

ini_set('log_errors', '1');
ini_set('error_log', '/proc/self/fd/2');

$pdo = Database::getConnection();
$userService = new UserService($pdo);

$rand = rand(100, 999);
$email = "user{$rand}@example.com";
$name = "Name Surname {$rand}";

appLog("Incoming request. Generated test user: {$email}");
$userService->registerUser($email, $name);
appLog("Request completed successfully for {$email}");

echo "<h1>Успешно!</h1>";
echo "<p>Пользователь $name ($email) сохранен вместе с событием Outbox в одной транзакции.</p>";
