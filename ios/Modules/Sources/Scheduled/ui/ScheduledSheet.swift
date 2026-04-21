import SwiftUI

@MainActor
public final class ScheduledViewModel: ObservableObject {
    @Published public private(set) var items: [ScheduledMessage] = []
    private let repo: ScheduledMessages
    public let roomId: Int64

    public init(repo: ScheduledMessages, roomId: Int64) {
        self.repo = repo
        self.roomId = roomId
    }

    public func refresh() async {
        items = await repo.list(roomId: roomId)
    }

    public func cancel(_ id: Int64) async {
        await repo.cancel(id: id)
        items.removeAll { $0.id == id }
    }
}

public struct ScheduledSheet: View {
    @StateObject private var vm: ScheduledViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var pickedDate = Date().addingTimeInterval(3600)
    @State private var showPicker = false
    private let onPickSendAt: (Date) -> Void

    public init(repo: ScheduledMessages, roomId: Int64,
                onPickSendAt: @escaping (Date) -> Void) {
        _vm = StateObject(wrappedValue: ScheduledViewModel(repo: repo, roomId: roomId))
        self.onPickSendAt = onPickSendAt
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 8) {
                if showPicker {
                    DatePicker("Send at", selection: $pickedDate, in: Date()...)
                        .datePickerStyle(.graphical)
                    Button("Confirm") {
                        onPickSendAt(pickedDate); dismiss()
                    }
                    .buttonStyle(.borderedProminent)
                } else {
                    Button("Schedule new…") { showPicker = true }
                        .buttonStyle(.borderedProminent)
                }
                List(vm.items) { m in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(Date(timeIntervalSince1970: TimeInterval(m.sendAt) / 1000),
                                 style: .time)
                                .font(.body.bold())
                            Text("ciphertext \(String(m.ciphertextB64.prefix(24)))…")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button(role: .destructive) {
                            Task { await vm.cancel(m.id) }
                        } label: { Image(systemName: "xmark.circle") }
                    }
                }
                .listStyle(.plain)
            }
            .padding()
            .navigationTitle("Scheduled")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Button("Close") { dismiss() }
                }
            }
            .task { await vm.refresh() }
        }
    }
}
