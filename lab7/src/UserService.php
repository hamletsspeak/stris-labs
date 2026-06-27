<?php
class UserService {
    private PDO $pdo;

    public function __construct(PDO $pdo) {
        $this->pdo = $pdo;
    }

    private function log(string $message): void {
        error_log('[USER_SERVICE][' . date('Y-m-d H:i:s') . '] ' . $message);
    }

    public function registerUser(string $email, string $name): void {
        try {
            $this->log("Starting transaction for {$email}");
            $this->pdo->beginTransaction();

            $stmt = $this->pdo->prepare("INSERT INTO users (email, name) VALUES (?, ?)");
            $stmt->execute([$email, $name]);
            $userId = $this->pdo->lastInsertId();
            $this->log("User inserted into users table with id={$userId}");

            $eventPayload = json_encode([
                'user_id' => $userId,
                'email' => $email,
                'registered_at' => date('c')
            ]);

            $outboxStmt = $this->pdo->prepare("
                INSERT INTO outbox (aggregate_type, aggregate_id, event_type, payload)
                VALUES ('User', ?, 'UserRegistered', ?)
            ");
            $outboxStmt->execute([$userId, $eventPayload]);
            $outboxId = $this->pdo->lastInsertId();
            $this->log("Outbox event saved with id={$outboxId} for user_id={$userId}");

            $this->pdo->commit();
            $this->log("Transaction committed successfully for user_id={$userId}");
        } catch (Exception $e) {
            if ($this->pdo->inTransaction()) {
                $this->pdo->rollBack();
            }
            $this->log("Transaction rolled back for {$email}. Error: " . $e->getMessage());
            throw $e;
        }
    }
}
