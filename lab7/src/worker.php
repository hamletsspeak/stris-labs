<?php
require_once 'Database.php';
require_once 'OutboxWorker.php';

function workerLog(string $message): void {
    echo '[WORKER_MAIN][' . date('Y-m-d H:i:s') . "] {$message}\n";
}

workerLog('Transactional Outbox worker is starting');

$pdo = null;

while ($pdo === null) {
    try {
        $pdo = Database::getConnection();
        workerLog('Database connection established');
    } catch (PDOException $e) {
        workerLog('Database is not ready yet. Retrying in 3 seconds');
        sleep(3);
    }
}

$worker = new OutboxWorker($pdo);

while (true) {
    try {
        $worker->processOutbox();
    } catch (Exception $e) {
        workerLog('Unhandled worker loop error: ' . $e->getMessage());
    }
    sleep(2);
}
