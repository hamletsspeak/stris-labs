<?php
class OutboxWorker {
    private PDO $pdo;

    public function __construct(PDO $pdo) {
        $this->pdo = $pdo;
    }

    private function log(string $message): void {
        echo '[OUTBOX_WORKER][' . date('Y-m-d H:i:s') . "] {$message}\n";
    }

    public function processOutbox(): void {
        $this->log('Polling outbox table');
        $this->pdo->beginTransaction();

        $stmt = $this->pdo->prepare("
            SELECT * FROM outbox
            WHERE status = 'PENDING'
            ORDER BY id ASC
            LIMIT 5
            FOR UPDATE SKIP LOCKED
        ");
        $stmt->execute();
        $events = $stmt->fetchAll();

        if (empty($events)) {
            $this->log('No pending events found');
            $this->pdo->commit();
            return;
        }

        $this->log('Fetched ' . count($events) . ' pending event(s) for processing');

        foreach ($events as $event) {
            try {
                $this->log("Sending event {$event['event_type']} from outbox_id={$event['id']} for aggregate_id={$event['aggregate_id']}");

                $deleteStmt = $this->pdo->prepare("DELETE FROM outbox WHERE id = ?");
                $deleteStmt->execute([$event['id']]);
                $this->log("Event outbox_id={$event['id']} processed and removed from outbox");
            } catch (Exception $e) {
                $updateStmt = $this->pdo->prepare("UPDATE outbox SET status = 'FAILED' WHERE id = ?");
                $updateStmt->execute([$event['id']]);
                $this->log("Failed to process outbox_id={$event['id']}: " . $e->getMessage());
            }
        }

        $this->pdo->commit();
        $this->log('Processing transaction committed');
    }
}
