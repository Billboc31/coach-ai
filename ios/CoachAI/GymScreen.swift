import SwiftUI

struct GymScreen: View {
    @EnvironmentObject private var app: AppStore
    @State private var deleting: Workout?
    var body: some View {
        Group {
            if app.workout != nil { SessionScreen() }
            else {
                List {
                    if let error = app.error { Section { Text(error).foregroundStyle(.red) } }
                    if app.busy { ProgressView("Chargement…") }
                    if let overview = app.overview {
                        let unfinished = overview.workouts.filter { !$0.locked }
                        if !unfinished.isEmpty {
                            Section("Reprendre une séance") {
                                ForEach(unfinished) { workout in
                                    Button { Task { await app.resume(workout) } } label: {
                                        Label(workout.title, systemImage: "play.circle.fill").padding(.vertical, 8)
                                    }.swipeActions {
                                        Button("Supprimer", role: .destructive) { deleting = workout }
                                    }
                                }
                            }
                        }
                        ForEach(overview.programs.filter { $0.archived != true }) { program in
                            Section(program.title) {
                                ForEach(program.availableDays) { day in
                                    Button { Task { await app.start(program: program.id, day: day.id) } } label: {
                                        VStack(alignment: .leading, spacing: 6) {
                                            Text(day.display_name ?? day.name).font(.headline)
                                            Text("\(day.exercises.filter { $0.hidden != true }.count) exercices · \(day.sheet)")
                                                .font(.caption).foregroundStyle(.secondary)
                                        }.padding(.vertical, 8)
                                    }
                                }
                            }
                        }
                        if overview.programs.isEmpty {
                            ContentUnavailableView("Aucun programme", systemImage: "dumbbell", description: Text("Importe ton Excel depuis l’app web. Il apparaîtra ici après actualisation."))
                        }
                        Section("Dernières séances terminées") {
                            ForEach(overview.workouts.filter(\.locked).prefix(10)) { workout in
                                Button { Task { await app.resume(workout) } } label: {
                                    Label(workout.title, systemImage: "checkmark.circle").padding(.vertical, 6)
                                }
                            }
                        }
                    }
                }.disabled(app.busy).refreshable { await app.refresh() }
                    .navigationTitle("Musculation")
                    .toolbar { Button { Task { await app.refresh() } } label: { Image(systemName: "arrow.clockwise") }.disabled(app.busy) }
                    .task { if app.overview == nil { await app.refresh() } }
            }
        }.confirmationDialog("Supprimer cette séance commencée ?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button("Supprimer définitivement", role: .destructive) {
                if let value = deleting { Task { await app.delete(value) } }; deleting = nil
            }
        }
    }
}

struct SessionScreen: View {
    @EnvironmentObject private var app: AppStore
    @EnvironmentObject private var clock: RestClock
    @State private var chooser = false
    @State private var progression = false
    @State private var finish = false
    @State private var reload = false
    @State private var deleting = false
    @State private var increase = 2.5
    @State private var manualRest = 90
    var body: some View {
        if let workout = app.workout, let exercise = app.exercise {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack {
                        Text("Exercice \(app.index + 1) / \(workout.exercises.count)")
                        Spacer()
                        Text(app.busy ? "Enregistrement…" : app.dirty ? "Brouillon sur l’iPhone" : "Enregistré")
                    }.font(.caption).foregroundStyle(.secondary)
                    ProgressView(value: Double((exercise.logged_sets ?? []).filter(\.done).count), total: Double(max(1, exercise.logged_sets?.count ?? 1)))
                    HStack(alignment: .top, spacing: 16) {
                        ExerciseImage(exercise: exercise).frame(width: 96, height: 96)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(exercise.title).font(.title2.bold()).fixedSize(horizontal: false, vertical: true)
                            Text(exercise.reps?.replacingOccurrences(of: "\n", with: " · ") ?? "Consigne libre")
                            if let tempo = exercise.tempo, !tempo.isEmpty { Text("Tempo \(tempo)").font(.caption) }
                        }
                    }
                    if let instruction = exercise.training_instruction, !instruction.isEmpty {
                        Text(instruction).font(.callout).foregroundStyle(.secondary)
                    }
                    if let convention = exercise.weight_convention {
                        Text(weightLabel(convention) + (exercise.weight_context.map { $0.isEmpty ? "" : " · \($0)" } ?? ""))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if exercise.is_document == true {
                        ForEach(exercise.document_links ?? [], id: \.self) { link in
                            if let url = URL(string: link), url.scheme == "https" { Link("Ouvrir la fiche d’exercices", destination: url) }
                        }
                    }
                    if let error = app.error { Text(error).foregroundStyle(.red).accessibilityLabel("Erreur : \(error)") }
                    if app.conflict {
                        Label("Brouillon conservé. Compare tes valeurs avec la version web avant de recharger.", systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
                    }
                    VStack(spacing: 16) {
                        ForEach(Array((exercise.logged_sets ?? []).enumerated()), id: \.offset) { i, row in
                            SetRow(number: i + 1, row: row, rest: exercise.restText(at: i), enabled: !workout.locked && !app.busy && !app.conflict,
                                setWeight: { value in app.edit(row: i) { $0.weight = value } },
                                setReps: { value in app.edit(row: i) { $0.reps = value } },
                                setSeconds: { value in app.edit(row: i) { $0.seconds = value } },
                                toggle: {
                                    app.edit(row: i) { $0.done.toggle() }
                                    if !row.done {
                                        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                                        if let seconds = CoachRules.restSeconds(exercise.restText(at: i)) { Task { await clock.start(seconds: seconds) } }
                                    }
                                    Task { await app.save() }
                                })
                        }
                    }.id(exercise.id)
                    if !workout.locked {
                        Button { app.addSet() } label: { Label("Ajouter une série", systemImage: "plus.circle") }
                            .disabled(app.busy || app.conflict || (exercise.logged_sets?.count ?? 0) >= 30)
                        restView
                    }
                    Button { chooser = true } label: { Label("Voir les \(workout.exercises.count) exercices", systemImage: "list.bullet") }
                    if !workout.locked {
                        Button("Terminer la séance") { finish = true }.buttonStyle(.borderedProminent).controlSize(.large)
                            .disabled(app.busy || app.conflict)
                        Button("Supprimer cette séance commencée", role: .destructive) { deleting = true }.disabled(app.busy)
                    }
                    Button("Recharger la version serveur") { reload = true }.font(.footnote).disabled(app.busy)
                }.padding()
            }.scrollDismissesKeyboard(.interactively).background(Color(.systemGroupedBackground))
                .navigationTitle(workout.title).navigationBarTitleDisplayMode(.inline)
                .toolbar(.hidden, for: .tabBar)
                .toolbar {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("OK") { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                    }
                    ToolbarItem(placement: .topBarLeading) {
                        Button("Quitter") { clock.cancel(); app.leave() }.disabled(app.dirty || app.busy)
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Enregistrer") { Task { await app.save() } }.disabled(workout.locked || !app.dirty || app.busy || app.conflict)
                    }
                }
                .safeAreaInset(edge: .bottom) {
                    HStack {
                        Button { app.select(app.index - 1) } label: { Label("Précédent", systemImage: "chevron.left") }.disabled(app.index == 0 || app.busy)
                        Spacer()
                        Button { next(exercise, workout: workout) } label: { Label("Suivant", systemImage: "chevron.right") }
                            .disabled(app.index + 1 >= workout.exercises.count || app.busy || app.conflict)
                    }.buttonStyle(.bordered).controlSize(.large).padding().background(.regularMaterial)
                }
                .sheet(isPresented: $chooser) {
                    NavigationStack {
                        List(Array(workout.exercises.enumerated()), id: \.element.id) { n, e in
                            Button { app.select(n); chooser = false } label: {
                                HStack { ExerciseImage(exercise: e).frame(width: 56, height: 56); Text(e.title); Spacer(); Text("\((e.logged_sets ?? []).filter(\.done).count)/\(e.logged_sets?.count ?? 0)").font(.caption) }
                            }.disabled(app.busy)
                        }.navigationTitle("Ta séance").toolbar { Button("Fermer") { chooser = false } }
                    }
                }
                .sheet(isPresented: $progression) {
                    NavigationStack {
                        Form {
                            Section {
                                Text("Augmenter la charge pour la prochaine séance ?").font(.headline)
                                Text("L’augmentation est ajoutée aux charges de référence de cet exercice. Les séries d’aujourd’hui restent inchangées.").font(.footnote)
                                Stepper("+\(increase.formatted()) kg", value: $increase, in: 0...100, step: 0.5)
                                Button("Enregistrer l’augmentation et continuer") {
                                    app.setIncrease(increase); progression = false; advance()
                                }.disabled(!(exercise.logged_sets ?? []).allSatisfy { ($0.weight ?? 0) + increase <= 2000 })
                                Button("Garder la même charge") { app.setIncrease(0); progression = false; advance() }
                            }
                        }.navigationTitle("Prochaine séance").toolbar { Button("Annuler") { progression = false } }
                    }.presentationDetents([.medium, .large])
                }
                .confirmationDialog("Terminer ? Seules les séries cochées compteront comme réalisées.", isPresented: $finish, titleVisibility: .visible) {
                    Button("Terminer et enregistrer") { Task { await app.save(finish: true); if app.workout?.locked == true { clock.cancel() } } }
                }
                .confirmationDialog("Abandonner le brouillon et recharger le serveur ?", isPresented: $reload, titleVisibility: .visible) {
                    Button("Recharger et remplacer le brouillon", role: .destructive) { Task { await app.reloadDiscardingDraft() } }
                }
                .confirmationDialog("Supprimer définitivement cette séance commencée ?", isPresented: $deleting, titleVisibility: .visible) {
                    Button("Supprimer", role: .destructive) { Task { await app.delete(workout); if app.workout == nil { clock.cancel() } } }
                }
                .onAppear { UIApplication.shared.isIdleTimerDisabled = !workout.locked }
                .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
                .onChange(of: workout.locked) { _, locked in UIApplication.shared.isIdleTimerDisabled = !locked }
        }
    }
    private var restView: some View {
        VStack(alignment: .leading, spacing: 10) {
            TimelineView(.periodic(from: .now, by: 1)) { context in
                if let deadline = clock.deadline {
                    let seconds = max(0, Int(ceil(deadline.timeIntervalSince(context.date))))
                    Text(seconds == 0 ? "Repos terminé" : "Repos · \(seconds / 60):\(String(format: "%02d", seconds % 60))")
                        .font(.title.monospacedDigit().bold()).accessibilityAddTraits(.updatesFrequently)
                } else { Text("Minuteur de repos").font(.headline) }
            }
            HStack {
                Stepper("\(manualRest) s", value: $manualRest, in: 5...7200, step: 5)
                Button("Démarrer") { Task { await clock.start(seconds: manualRest) } }
            }
            if clock.deadline != nil { Button("Passer le repos") { clock.cancel() } }
            if clock.notificationDenied { Text("Notifications désactivées : le minuteur reste visible ici.").font(.caption) }
        }.padding().frame(maxWidth: .infinity, alignment: .leading).background(.background, in: RoundedRectangle(cornerRadius: 18))
    }
    private func next(_ exercise: Exercise, workout: Workout) {
        guard !workout.locked else { app.select(app.index + 1); return }
        let rows = exercise.logged_sets ?? []
        if !rows.isEmpty && rows.allSatisfy(\.done) && rows.contains(where: { $0.weight != nil }) {
            increase = app.progression[exercise.id] ?? exercise.next_load_increase_kg ?? 2.5; progression = true
        } else { advance() }
    }
    private func advance() {
        Task {
            if app.dirty { await app.save() }
            if !app.dirty && !app.conflict { app.select(app.index + 1) }
        }
    }
    private func weightLabel(_ value: String) -> String {
        ["total": "Charge totale", "per_dumbbell": "Charge par haltère", "added": "Charge ajoutée", "machine": "Charge indiquée par la machine", "bodyweight": "Poids du corps", "unspecified": "Convention de charge à vérifier"][value] ?? "Convention de charge à vérifier"
    }
}

struct SetRow: View {
    let number: Int
    let row: LoggedSet
    let rest: String
    let enabled: Bool
    let setWeight: (Double?) -> Void
    let setReps: (Int?) -> Void
    let setSeconds: (Int?) -> Void
    let toggle: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack { Text("Série \(number)").font(.headline); Spacer(); if row.done { Label("Faite", systemImage: "checkmark.circle.fill").foregroundStyle(.green) } }
            HStack(alignment: .bottom, spacing: 12) {
                VStack(alignment: .leading) {
                    Text("kg").font(.caption)
                    TextField("—", value: Binding(get: { row.weight }, set: setWeight), format: .number)
                        .keyboardType(.decimalPad).accessibilityLabel("Poids série \(number)")
                }
                VStack(alignment: .leading) {
                    Text("Répétitions").font(.caption)
                    TextField("—", value: Binding(get: { row.reps }, set: setReps), format: .number)
                        .keyboardType(.numberPad).accessibilityLabel("Répétitions série \(number)")
                }
                Button(action: toggle) { Image(systemName: row.done ? "checkmark.circle.fill" : "circle").font(.largeTitle).frame(minWidth: 52, minHeight: 52) }
                    .accessibilityLabel(row.done ? "Décocher la série \(number)" : "Valider la série \(number)")
                    .disabled(!enabled || (!row.done && (row.reps == nil && row.seconds == nil || !row.valid)))
            }.textFieldStyle(.roundedBorder).font(.title2.monospacedDigit()).disabled(!enabled)
            DisclosureGroup("Durée / gainage") {
                HStack { Text("Secondes"); TextField("—", value: Binding(get: { row.seconds }, set: setSeconds), format: .number).keyboardType(.numberPad).textFieldStyle(.roundedBorder).disabled(!enabled) }
            }.font(.caption)
            Text(rest.isEmpty ? "Repos non précisé" : "Repos après cette série : \(rest)").font(.caption).foregroundStyle(.secondary)
        }.padding().background(row.done ? Color.green.opacity(0.08) : Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 18))
    }
}
struct ExerciseImage: View {
    let exercise: Exercise
    var body: some View {
        Group {
            if let thumbnail = exercise.thumbnail, let url = URL(string: thumbnail.url), url.scheme == "https" {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().scaledToFit() }
                    else { Image(systemName: "dumbbell.fill").resizable().scaledToFit().padding(18).foregroundStyle(.secondary) }
                }.accessibilityLabel("\(exercise.title) · \(thumbnail.credit.authors.joined(separator: ", ")) · \(thumbnail.credit.name)")
            } else { Image(systemName: exercise.is_document == true ? "doc.text" : "dumbbell.fill").resizable().scaledToFit().padding(18).foregroundStyle(.secondary) }
        }.background(Color.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
    }
}
