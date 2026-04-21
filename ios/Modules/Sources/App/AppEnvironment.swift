import Foundation
import VortexCrypto
import Bootstrap
import Net
import Auth
import Identity
import DB
import Rooms
import Keys
import WS
import Chat
import Files
import Stickers
import Calls
import Push
import Federation
import Search
import Spaces
import Bots
import Threads
import Feeds
import Settings
import I18N
import Emoji
import Drafts
import Folders
import Accounts
import SavedGifs
import Contacts
import Scheduled
import Premium
import Reactions

/// Composition root. Builds the whole graph in dependency order.
@MainActor
public final class AppEnvironment {

    public static let shared = AppEnvironment()

    public let version: String = "0.1.0"

    public let crypto: VortexCryptoFactory
    public let bootstrap: BootstrapFactory
    public let auth: AuthFactory
    public let identity: IdentityFactory
    public let db: DBFactory
    public let rooms: RoomsFactory
    public let keysF: KeysFactory
    public let ws: WSFactory
    public let search: SearchFactory
    public let chat: ChatFactory
    public let files: FilesFactory
    public let calls: CallsFactory
    public let stickers: StickersFactory
    public let push: PushFactory
    public let federation: FederationFactory
    public let spaces: SpacesFactory
    public let bots: BotsFactory
    public let threads: ThreadsFactory
    public let feeds: FeedsFactory
    public let settings: SettingsFactory
    public let i18n: I18NFactory
    public let emoji: EmojiFactory
    public let drafts: DraftsFactory
    public let folders: FoldersFactory
    public let accounts: AccountsFactory
    public let savedGifs: SavedGifsFactory
    public let contacts: ContactsFactory
    public let scheduled: ScheduledFactory
    public let premium: PremiumFactory
    public let reactions: ReactionsFactory
    public let http: HttpClient
    public let cryptoPreview: CryptoPreview

    private init() {
        let crypto = VortexCryptoFactory()
        let bootstrap = BootstrapFactory()
        let baseProv  = BaseUrlProviderFromPrefs(prefs: bootstrap.prefs)
        let auth = AuthFactory(baseUrlProvider: baseProv, crypto: crypto)

        self.crypto = crypto
        self.bootstrap = bootstrap
        self.auth = auth
        self.http = auth.http
        self.cryptoPreview = CryptoPreview.makeFrom(crypto: crypto)

        do { self.identity = try IdentityFactory(crypto: crypto, store: auth.store) }
        catch { fatalError("Identity factory failed: \(error)") }

        do { self.db = try DBFactory() }
        catch { fatalError("DB factory failed: \(error)") }

        self.rooms = RoomsFactory(http: auth.http, db: db, crypto: crypto, identity: identity.repo)
        self.keysF = KeysFactory(http: auth.http, db: db)
        self.ws = WSFactory(base: baseProv, tokens: auth.tokens)
        self.search = SearchFactory(db: db)
        // Threads is built before Chat so MessageActions can create
        // threads on demand from a long-press.
        self.threads = ThreadsFactory(http: auth.http, db: db)
        self.chat = ChatFactory(
            ws: ws.client, crypto: crypto,
            keys: keysF.provider, db: db,
            http: auth.http, searchRepo: search.repo,
            threads: threads.repo,
        )
        self.files = FilesFactory(http: auth.http, crypto: crypto, keys: keysF.provider)
        self.calls = CallsFactory(http: auth.http, ws: ws.client)
        self.stickers = StickersFactory(http: auth.http)
        self.push = PushFactory(http: auth.http, crypto: crypto)
        self.federation = FederationFactory(http: auth.http)
        self.spaces = SpacesFactory(http: auth.http, db: db)
        self.bots = BotsFactory(http: auth.http, db: db)
        // `self.threads` already initialised above before Chat so the
        // action-create-thread flow has it in hand at construction time.
        self.feeds = FeedsFactory(http: auth.http, db: db)
        self.settings = SettingsFactory(db: db, identity: identity.repo, auth: auth.repo)
        self.i18n = I18NFactory()
        self.emoji = EmojiFactory()
        self.drafts = DraftsFactory(http: auth.http)
        self.folders = FoldersFactory()
        self.savedGifs = SavedGifsFactory(http: auth.http)
        self.contacts = ContactsFactory(http: auth.http)
        self.scheduled = ScheduledFactory(http: auth.http)
        self.premium = PremiumFactory(http: auth.http)
        self.reactions = ReactionsFactory()
        // Accounts: the http-factory closure returns the same shared
        // client — a real multi-node implementation would instantiate a
        // fresh URLSessionHttpClient pointed at the new baseUrl. The
        // active-change callback lets App reset the chat/WS stack.
        self.accounts = AccountsFactory(
            store: auth.store,
            http: { _ in auth.http },
            onActiveChanged: { _, _ in },
        )
    }
}

public struct CryptoPreview {
    public let x25519Short: String
    public let ed25519Short: String

    static func makeFrom(crypto: VortexCryptoFactory) -> CryptoPreview {
        let x = crypto.keyAgreement.generateKeyPair()
        let e = crypto.signer.generateKeyPair()
        return .init(
            x25519Short: String(Hex.encode(x.publicKey).prefix(16)),
            ed25519Short: String(Hex.encode(e.publicKey).prefix(16)),
        )
    }
}
