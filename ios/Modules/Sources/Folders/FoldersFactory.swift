import Foundation

public struct FoldersFactory {
    public let folders: Folders
    public init() { self.folders = UserDefaultsFolders() }
}
