import Foundation
import Net

public struct ContactsFactory {
    public let contacts: Contacts
    public init(http: HttpClient) { self.contacts = HttpContacts(http: http) }
}
