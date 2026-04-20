import Foundation
import GRDB

/// Decrypted (or pending-decrypt) message cached locally.
public struct MessageRecord: Codable, FetchableRecord, MutablePersistableRecord, Equatable, Sendable {
    public var id: Int64
    public var roomId: Int64
    public var senderId: Int64?
    public var senderUsername: String?
    public var msgType: String
    public var plaintext: String?         // nil = not yet decrypted (key pending)
    public var ciphertextHex: String
    public var sentAt: Int64              // epoch millis
    public var editedAt: Int64?
    public var replyTo: Int64?

    public static let databaseTableName = "messages"

    public init(
        id: Int64, roomId: Int64,
        senderId: Int64? = nil, senderUsername: String? = nil,
        msgType: String = "text",
        plaintext: String?, ciphertextHex: String,
        sentAt: Int64, editedAt: Int64? = nil, replyTo: Int64? = nil,
    ) {
        self.id = id
        self.roomId = roomId
        self.senderId = senderId
        self.senderUsername = senderUsername
        self.msgType = msgType
        self.plaintext = plaintext
        self.ciphertextHex = ciphertextHex
        self.sentAt = sentAt
        self.editedAt = editedAt
        self.replyTo = replyTo
    }
}
