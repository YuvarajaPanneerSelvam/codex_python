"""Python UI for campus modules, separate from transport screens."""
from datetime import date
from nicegui import app, ui
from campus import Campus


def register_campus(transport):
    campus = Campus(transport)

    @ui.page('/campus')
    def campus_page():
        ui.colors(primary='#12685e')
        ui.query('body').classes('bg-slate-50 text-slate-800')
        user = transport.user(app.storage.user.get('user_id'))
        with ui.header().classes('bg-white text-slate-800 border-b shadow-none'):
            ui.label('Campus Hub').classes('text-xl font-bold')
            ui.button('Back to transport', icon='directions_bus', on_click=lambda: ui.navigate.to('/')).props('flat')
        with ui.column().classes('w-full max-w-6xl mx-auto p-4 md:p-8 gap-5'):
            ui.label('Your connected campus').classes('text-3xl font-bold')
            ui.label('Energy, leave and learning in one place.').classes('text-slate-500')
            if not user:
                ui.label('Sign in through the transport app to use campus modules.')
                ui.button('Go to sign in', on_click=lambda: ui.navigate.to('/'))
                return
            actor = user['id']
            energy_access = campus.can(actor, 'energy')
            leave_access = campus.can(actor, 'leave_manager')
            training_access = campus.can(actor, 'training_manager')

            def act(callback, message):
                try:
                    if app.storage.user.get('user_id') != actor:
                        raise ValueError('Your session changed. Sign in again.')
                    callback()
                    ui.notify(message, type='positive')
                    panels.refresh()
                except ValueError as exc:
                    ui.notify(str(exc), type='warning')

            def table(rows, columns):
                ui.table(columns=[{'name': key, 'label': label, 'field': key, 'sortable': True} for key, label in columns], rows=rows, pagination=10).classes('w-full')

            with ui.tabs().classes('w-full') as tabs:
                leave_tab = ui.tab('Time-sheet', icon='event_available')
                training_tab = ui.tab('Training', icon='school')
                energy_tab = ui.tab('Energy', icon='solar_power') if energy_access else None
                compute_tab = ui.tab('Compute', icon='computer')
                access_tab = ui.tab('Access', icon='manage_accounts') if user['role'] == 'admin' else None

            @ui.refreshable
            def panels():
                with ui.tab_panels(tabs, value=tabs.value or leave_tab).classes('w-full bg-transparent'):
                    with ui.tab_panel(leave_tab).classes('p-0'):
                        ui.label('Leave & holidays').classes('text-2xl font-bold')
                        ui.label('Time-sheet starts with leave tracking; hourly time entries and payroll are not included.').classes('text-sm text-slate-500')
                        with ui.card().classes('w-full p-5 shadow-none border'):
                            ui.label('Campus rules & engagements').classes('text-lg font-semibold')
                            ui.label(campus.rules(actor)).classes('whitespace-pre-wrap')
                        with ui.expansion('Request leave', icon='add').classes('w-full border bg-white rounded-lg'):
                            kind = ui.select({'regular': 'Regular leave', 'medical': 'Medical leave'}, value='regular', label='Leave type').classes('w-full')
                            start = ui.input('Leave start date', value=date.today().isoformat()).props('type=date')
                            end = ui.input('Leave end date', value=date.today().isoformat()).props('type=date')
                            reason = ui.textarea('Leave reason').classes('w-full')
                            ui.label('Give only necessary details; do not include medical reports. Requests are visible to you and leave managers. Working days use Monday–Friday, excluding holidays.').classes('text-xs text-slate-500')
                            ui.button('Submit leave request', on_click=lambda: act(lambda: campus.request_leave(actor, kind.value, start.value, end.value, reason.value), 'Leave request submitted.'))
                        own = campus.leaves(actor)
                        ui.label('My leave requests').classes('text-lg font-semibold')
                        table(own, [('id', 'Request'), ('kind', 'Type'), ('start_day', 'From'), ('end_day', 'To'), ('working_days', 'Days'), ('status', 'Status'), ('review_note', 'Review note')])
                        for request in own:
                            if request['status'] == 'pending':
                                ui.button(f"Cancel request #{request['id']}", on_click=lambda r=request: act(lambda: campus.cancel_leave(actor, r['id']), 'Request cancelled.')).props('flat')
                        ui.label('Holiday calendar').classes('text-lg font-semibold')
                        table(campus.holidays(actor), [('day', 'Date'), ('name', 'Holiday')])
                        if leave_access:
                            with ui.expansion('Manage holidays & rules', icon='settings').classes('w-full border bg-white rounded-lg'):
                                holiday_day = ui.input('Holiday date', value=date.today().isoformat()).props('type=date')
                                holiday_name = ui.input('Holiday name').classes('w-full')
                                ui.button('Add holiday', on_click=lambda: act(lambda: campus.add_holiday(actor, holiday_day.value, holiday_name.value), 'Holiday added.'))
                                rules = ui.textarea('Campus leave rules', value=campus.rules(actor)).classes('w-full')
                                ui.button('Save leave rules', on_click=lambda: act(lambda: campus.set_rules(actor, rules.value), 'Rules saved.'))
                            ui.label('Leave approval desk').classes('text-xl font-semibold')
                            for request in campus.leaves(actor, management=True):
                                with ui.card().classes('w-full p-4 shadow-none border'):
                                    ui.label(f"#{request['id']} · {request['member']} · {request['kind']} · {request['status']}").classes('font-semibold')
                                    ui.label(f"{request['start_day']} → {request['end_day']} · {request['working_days']} working days")
                                    ui.label(request['reason']).classes('whitespace-pre-wrap')
                                    if request['status'] == 'pending' and request['user_id'] != actor:
                                        note = ui.input(f"Review note for request {request['id']}").classes('w-full')
                                        with ui.row():
                                            ui.button(f"Approve #{request['id']}", on_click=lambda r=request, n=note: act(lambda: campus.review_leave(actor, r['id'], 'approved', n.value), 'Leave approved.'))
                                            ui.button(f"Reject #{request['id']}", on_click=lambda r=request, n=note: act(lambda: campus.review_leave(actor, r['id'], 'rejected', n.value), 'Leave rejected.')).props('outline')
                                    elif request['review_note']:
                                        ui.label('Review: ' + request['review_note'])
                    with ui.tab_panel(training_tab).classes('p-0'):
                        ui.label('Campus training').classes('text-2xl font-bold')
                        person = campus.person(actor)
                        ui.label(f"Assigned audience: {person['academic_role']} · Industry: {person['industry'] or 'not assigned'}").classes('text-slate-500')
                        ui.label('An administrator assigns your role and industry. Completion is self-reported, not a certified qualification.').classes('text-sm text-slate-500')
                        courses = campus.trainings(actor)
                        if not courses:
                            ui.label('No training is available for your assigned role or industry yet.')
                        for course in courses:
                            with ui.card().classes('w-full p-5 shadow-none border'):
                                ui.label(course['title']).classes('text-lg font-semibold')
                                ui.label(f"{course['kind'].title()} based · {course['target']}" + ('' if course['active'] else ' · Archived')).classes('text-teal-700')
                                ui.label(course['description']).classes('whitespace-pre-wrap')
                                if course['enrollment']:
                                    ui.badge(course['enrollment'])
                                    if course['enrollment'] == 'enrolled':
                                        ui.button('Mark training complete', on_click=lambda c=course: act(lambda: campus.complete(actor, c['id']), 'Training marked complete.'))
                                elif course['active'] and campus.eligible(person, course):
                                    ui.button('Enroll in training', on_click=lambda c=course: act(lambda: campus.enroll(actor, c['id']), 'Enrollment confirmed.'))
                                if training_access and course['active']:
                                    ui.button('Archive training', on_click=lambda c=course: act(lambda: campus.archive_training(actor, c['id']), 'Training archived.')).props('flat')
                        if training_access:
                            with ui.expansion('Create training', icon='add').classes('w-full bg-white border rounded-lg'):
                                title = ui.input('Training title').classes('w-full')
                                audience_type = ui.select({'role': 'Role based', 'industry': 'Industry based'}, value='role', label='Training audience type').classes('w-full')
                                target = ui.input('Target role or industry', value='student').classes('w-full')
                                ui.label('For role based training use student, staff, admin or all. For industry based training enter the assigned industry, for example manufacturing.').classes('text-xs text-slate-500')
                                description = ui.textarea('Training description').classes('w-full')
                                ui.button('Publish training', on_click=lambda: act(lambda: campus.add_training(actor, title.value, audience_type.value, target.value, description.value), 'Training published.'))
                            ui.label('Training participation').classes('text-xl font-semibold')
                            table(campus.training_roster(actor), [('title', 'Training'), ('name', 'Member'), ('status', 'Progress')])
                    if energy_tab:
                        with ui.tab_panel(energy_tab).classes('p-0'):
                            ui.label('Campus energy').classes('text-2xl font-bold')
                            ui.label('Restricted energy ledger · Green generation, consumption, storage and distribution').classes('text-teal-700')
                            ui.label('Manual meter readings only. This module records energy flows; it does not control electrical equipment or connect to live meters. All values are kWh.').classes('text-sm text-slate-500')
                            readings = campus.energy(actor)
                            latest = {}
                            for entry in readings:
                                latest.setdefault(entry['campus'], entry)
                            with ui.row().classes('w-full gap-4'):
                                for entry in latest.values():
                                    with ui.card().classes('p-5 border shadow-none'):
                                        ui.label(entry['campus']).classes('font-semibold')
                                        ui.label(f"{entry['closing']:g} kWh stored").classes('text-xl text-teal-700')
                                        ui.label('As of ' + entry['day']).classes('text-xs')
                            with ui.expansion('Record energy reading', icon='add').classes('w-full bg-white border rounded-lg'):
                                name = ui.input('Energy campus', value='Main Campus').classes('w-full')
                                day = ui.input('Reading date', value=date.today().isoformat()).props('type=date')
                                source = ui.select(['solar', 'wind', 'biogas', 'mixed', 'other'], value='solar', label='Energy source').classes('w-full')
                                fields = {}
                                with ui.grid().classes('w-full grid-cols-1 md:grid-cols-2 gap-3'):
                                    for key, label in [('produced', 'Produced kWh'), ('consumed', 'Consumed kWh'), ('charged', 'Battery charged kWh'), ('discharged', 'Battery discharged kWh'), ('distributed', 'Distributed / exported kWh'), ('losses', 'Losses kWh'), ('initial', 'Initial stored kWh (first reading only)')]:
                                        fields[key] = ui.number(label, value=0, min=0, precision=3).classes('w-full')
                                destination = ui.input('Distribution destination (building / grid)').classes('w-full')
                                ui.label('Production + discharge must equal consumption + charge + distribution + losses. Stored balance carries forward. Entries are append-only; use a later date after the first reading.').classes('text-xs text-slate-500')
                                ui.button('Save energy reading', on_click=lambda: act(lambda: campus.record_energy(actor, name.value, day.value, source.value, *[fields[k].value for k in ('produced', 'consumed', 'charged', 'discharged', 'distributed', 'losses', 'initial')], destination=destination.value), 'Energy reading saved.'))
                            table(readings, [('campus', 'Campus'), ('day', 'Date'), ('source', 'Source'), ('produced', 'Produced kWh'), ('consumed', 'Consumed kWh'), ('charged', 'Charged kWh'), ('discharged', 'Discharged kWh'), ('distributed', 'Distributed kWh'), ('destination', 'Destination'), ('losses', 'Losses kWh'), ('opening', 'Opening kWh'), ('closing', 'Stored kWh')])
                    with ui.tab_panel(compute_tab).classes('p-0'):
                        ui.label('Campus compute').classes('text-2xl font-bold')
                        ui.label('Requirements pending').classes('text-amber-700 font-medium')
                        ui.label('This is a reserved module. Compute resources, job scheduling and billing are not implemented; define those requirements in the next phase.')
                    if access_tab:
                        with ui.tab_panel(access_tab).classes('p-0'):
                            ui.label('Member roles & access').classes('text-2xl font-bold')
                            ui.label('Only administrators can change module access, academic roles and industry assignments.').classes('text-sm text-slate-500')
                            members = campus.members(actor)
                            member = ui.select({r['id']: f"{r['name']} · {r['email']}" for r in members}, label='Member').classes('w-full')

                            def edit_member():
                                try:
                                    profile = campus.profile(actor, member.value)
                                except ValueError as exc:
                                    ui.notify(str(exc), type='warning')
                                    return
                                with ui.dialog() as dialog, ui.card().classes('w-96 max-w-full p-6'):
                                    ui.label(profile['name']).classes('text-xl font-bold')
                                    academic = ui.select(['student', 'staff'], value=profile['academic_role'], label='Academic role').classes('w-full')
                                    industry = ui.input('Assigned industry', value=profile['industry']).classes('w-full')
                                    checks = {key: ui.checkbox(label, value=key in profile['permissions']).props(f'aria-label="{label}"') for key, label in [('energy', 'Energy access'), ('leave_manager', 'Leave manager'), ('training_manager', 'Training manager')]}
                                    ui.label('Existing administrators retain all module permissions. This does not grant the administrator role.').classes('text-xs text-slate-500')
                                    def save():
                                        def update():
                                            campus.set_profile(actor, profile['id'], academic.value, industry.value, [key for key, check in checks.items() if check.value])
                                            dialog.close()
                                        act(update, 'Member access saved.')
                                    ui.button('Save member access', on_click=save)
                                    ui.button('Cancel', on_click=dialog.close).props('flat')
                                dialog.open()
                            ui.button('Edit member access', on_click=edit_member)
            panels()
