// SPDX-License-Identifier: MIT
// Extrae un paquete Qt a disco conservando sus rutas virtuales.
#include <QCoreApplication>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QResource>
#include <QTextStream>

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const auto args = app.arguments();
    if (args.size() != 3 || !QResource::registerResource(args[1])) return 2;
    QDir output(args[2]);
    if (!output.mkpath(".")) return 3;
    QDirIterator it(":/", QDir::Files, QDirIterator::Subdirectories);
    int count = 0;
    while (it.hasNext()) {
        const auto source = it.next();
        const auto relative = source.mid(2);
        const auto target = output.filePath(relative);
        if (QFile::exists(target)) return 4; // No sobrescribir una extracción anterior.
        if (!QDir().mkpath(QFileInfo(target).path())) return 5;
        QFile input(source), dest(target);
        if (!input.open(QIODevice::ReadOnly) || !dest.open(QIODevice::WriteOnly)) return 6;
        auto data = input.readAll();
        if (dest.write(data) != data.size()) return 7;
        ++count;
    }
    QTextStream(stdout) << count << " archivos extraídos\n";
    return 0;
}
