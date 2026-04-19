// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CalcieMenuBar",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "CalcieMenuBar", targets: ["CalcieMenuBar"])
    ],
    targets: [
        .executableTarget(
            name: "CalcieMenuBar",
            path: "Sources"
        )
    ]
)

