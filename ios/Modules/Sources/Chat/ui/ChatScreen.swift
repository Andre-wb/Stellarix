import SwiftUI
#if canImport(UIKit)
import UIKit
#endif
import DB
import Threads
import Emoji

/// Wave 12 chat UI. LazyVStack + ScrollViewReader for auto-scroll;
/// text composer at the bottom; long-press context menu on each bubble
/// exposes reply / edit / delete / react / copy / open-thread.
@MainActor
public final class ChatViewModel: ObservableObject {
    @Published public private(set) var messages: [MessageRecord] = []
    @Published public var draft: String = ""
    @Published public var pendingThread: Threads.Thread?     // set when Open Thread succeeds

    public let roomId: Int64
    private let sender: MessageSender
    private let incoming: IncomingMessages
    private let actions: MessageActions
    private var observer: Task<Void, Never>?

    public init(roomId: Int64, sender: MessageSender, incoming: IncomingMessages, actions: MessageActions) {
        self.roomId = roomId
        self.sender = sender
        self.incoming = incoming
        self.actions = actions
    }

    public func start() {
        observer?.cancel()
        observer = Task { [roomId, incoming] in
            for await rows in incoming.messagesIn(roomId) {
                await MainActor.run { self.messages = rows }
            }
        }
    }
    public func stop() { observer?.cancel(); observer = nil }

    public func submit() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        _ = await sender.send(roomId: roomId, plaintext: text)
    }

    public func react(_ msg: MessageRecord, emoji: String) async {
        _ = await actions.react(messageId: msg.id, emoji: emoji)
    }
    public func delete(_ msg: MessageRecord) async {
        _ = await actions.delete(messageId: msg.id)
    }
    public func reply(to msg: MessageRecord, text: String) async {
        _ = await actions.reply(roomId: roomId, replyToMessageId: msg.id, plaintext: text)
    }
    public func edit(_ msg: MessageRecord, newText: String) async {
        _ = await actions.edit(messageId: msg.id, newPlaintext: newText)
    }

    /// Creates a real thread rooted at `msg` via the server and, on
    /// success, publishes it to [pendingThread] so the view can navigate.
    public func openThread(_ msg: MessageRecord) async {
        let title = msg.plaintext.map { String($0.prefix(40)) }
        if let t = await actions.openThread(messageId: msg.id, title: title) {
            await MainActor.run { self.pendingThread = t }
        }
    }

    public func clearPendingThread() { pendingThread = nil }
}

public struct ChatScreen: View {
    @StateObject private var vm: ChatViewModel
    /// Called when the user taps "Open thread" and the server confirms
    /// creation. The parent router pushes a new ChatScreen at the
    /// thread's virtual room id.
    private let onOpenThread: (Threads.Thread) -> Void
    private let emojiCatalog: EmojiCatalog
    @State private var emojiOpen = false

    public init(
        roomId: Int64,
        sender: MessageSender,
        incoming: IncomingMessages,
        actions: MessageActions,
        emojiCatalog: EmojiCatalog,
        onOpenThread: @escaping (Threads.Thread) -> Void = { _ in },
    ) {
        _vm = StateObject(wrappedValue: ChatViewModel(
            roomId: roomId, sender: sender, incoming: incoming, actions: actions,
        ))
        self.emojiCatalog = emojiCatalog
        self.onOpenThread = onOpenThread
    }

    public var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        ForEach(vm.messages, id: \.id) { msg in
                            Bubble(msg: msg)
                                .id(msg.id)
                                .contextMenu {
                                    Button {
                                        #if canImport(UIKit)
                                        UIPasteboard.general.string = msg.plaintext ?? ""
                                        #endif
                                    } label: { Label("Copy", systemImage: "doc.on.doc") }
                                    Button("👍") { Task { await vm.react(msg, emoji: "👍") } }
                                    Button("❤️") { Task { await vm.react(msg, emoji: "❤️") } }
                                    Button("🔥") { Task { await vm.react(msg, emoji: "🔥") } }
                                    Button {
                                        Task { await vm.openThread(msg) }
                                    } label: { Label("Open thread", systemImage: "text.bubble") }
                                    Button(role: .destructive) {
                                        Task { await vm.delete(msg) }
                                    } label: { Label("Delete", systemImage: "trash") }
                                }
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                }
                .onChange(of: vm.messages.count) { _, _ in
                    if let last = vm.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }
            Divider().background(.white.opacity(0.1))
            HStack {
                TextField("Message", text: $vm.draft)
                    .textFieldStyle(.roundedBorder)
                Button { emojiOpen.toggle() } label: { Text("😀") }
                    .accessibilityLabel(emojiOpen ? "Hide emoji" : "Show emoji")
                Button {
                    Task { await vm.submit() }
                } label: {
                    Image(systemName: "paperplane.fill")
                        .foregroundStyle(Color(red: 0x7C/255, green: 0x3A/255, blue: 0xED/255))
                }
                .disabled(vm.draft.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(8)
            if emojiOpen {
                EmojiPickerView(catalog: emojiCatalog) { e in
                    vm.draft += e
                }
            }
        }
        .background(Color(red: 0x07/255, green: 0x07/255, blue: 0x0E/255).ignoresSafeArea())
        .navigationTitle("Room #\(vm.roomId)")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .onAppear { vm.start() }
        .onDisappear { vm.stop() }
        .onChange(of: vm.pendingThread) { _, created in
            guard let created else { return }
            onOpenThread(created)
            vm.clearPendingThread()
        }
    }
}

private struct Bubble: View {
    let msg: MessageRecord
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(msg.senderUsername ?? "—")
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.55))
                Text(Date(timeIntervalSince1970: TimeInterval(msg.sentAt) / 1000),
                     style: .time)
                    .font(.caption2)
                    .foregroundStyle(.white.opacity(0.35))
                if msg.editedAt != nil {
                    Text("· edited")
                        .font(.caption2)
                        .foregroundStyle(.white.opacity(0.35))
                }
            }
            if let replyTo = msg.replyTo {
                Text("↵ reply to #\(replyTo)")
                    .font(.caption2)
                    .foregroundStyle(Color(red: 0xA8/255, green: 0x55/255, blue: 0xF7/255))
            }
            Text(msg.plaintext ?? "(decrypting…)")
                .foregroundStyle(.white)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
    }
}
