from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import random  # הוספתי לייבוא כדי ליצור מיקומים אקראיים לזומבים

app = Ursina()

# --- Setup ---
window.title = "Minecraft Clone"
window.exit_button.visible = False
window.fullscreen = True

# Block Data
BLOCK_TYPES = [
    {'name': 'Grass', 'texture': 'grass', 'color': color.white, 'break_time': 0.5},
    {'name': 'Stone', 'texture': 'warm-limestone-texture', 'color': color.rgb(180, 180, 180), 'break_time': 2.0},
    {'name': 'Wood', 'texture': 'natural-wooden-background', 'color': color.rgb(140, 90, 40), 'break_time': 1.0},
    {'name': 'Brick', 'texture': 'background-brick-wall.jpg', 'color': color.rgb(200, 100, 100), 'break_time': 1.5},
    {'name': 'Water', 'texture': 'white_cube', 'color': color.rgba(0, 100, 255, 150), 'break_time': 0.1},
]

# Global Variables
selected_index = 0
current_block = None
break_timer = 0
place_cooldown = 0
last_safe_position = Vec3(0, 0, 0)
reach_distance = 7
last_hovered = None

hit_sound = Audio('mine-stone-with-a-pickaxe-333694.mp3', loop=True, autoplay=False)
respawn_sound = Audio('item_respawn-91422.mp3', loop=False, autoplay=False)
damage_sound = Audio('suffering-damage-284365.mp3', loop=False, autoplay=False)
background_sound = Audio('background-music-224633.mp3',loop=True,autoplay=True)


# --- Zombie Class ---
class Zombie(Entity):
    def __init__(self, position=(0, 1, 0)):
        super().__init__(
            model='cube', color=color.green, texture='brick',
            position=position,
            scale=(1, 2, 1),
            origin_y=-0.5,  # הופך את התחתית שלו לנקודת המיקום
            collider='box'
        )
        self.hp = 100
        self.max_hp = 100
        self.knockback_direction = Vec3(0, 0, 0)
        self.knockback_intensity = 0
        self.fall_speed = 0  # מהירות הנפילה הנוכחית

        # מד בריאות
        self.health_bar_bg = Entity(parent=self, model='quad', color=color.black, scale=(1.2, 0.1),
                                    position=(0, 1.2, 0), billboard=True)
        self.health_bar = Entity(parent=self.health_bar_bg, model='quad', color=color.red, scale=(1, 1),
                                 position=(0, 0, -0.01), origin_x=-0.5, x=-0.5)

    def update_hp_bar(self):
        self.health_bar.scale_x = max(0, self.hp / self.max_hp)

    def take_damage(self, amount, knock_from=None):
        self.hp -= amount
        self.update_hp_bar()
        damage_sound.play()
        invoke(damage_sound.stop, delay=1)

        if knock_from:
            self.knockback_direction = (self.world_position - knock_from).normalized()
            self.knockback_intensity = 8

        original_color = self.color
        self.color = color.red
        invoke(setattr, self, 'color', original_color, delay=0.1)
        if self.hp <= 0:
            destroy(self)

    def update(self):
        # 1. לוגיקת כוח משיכה (Gravity)
        # יורים קרן מהמרכז של הזומבי כלפי מטה
        # ה-distance הוא 1.0 כי גובה הזומבי הוא 2 (המרכז הוא ב-1)
        ray = raycast(self.world_position + Vec3(0, 0.1, 0), Vec3(0, -1, 0), distance=1.1, ignore=(self,))

        if not ray.hit:
            # אם אין כלום מתחת לזומבי - הוא נופל
            self.fall_speed += 20 * time.dt  # האצה כלפי מטה
            self.y -= self.fall_speed * time.dt
        else:
            # אם הוא נגע בקרקע - הוא עוצר
            self.fall_speed = 0
            # יישור קטן כדי שלא ישקע בבלוק
            self.y = ray.point.y

            # 2. טיפול ב-Knockback
        if self.knockback_intensity > 0:
            self.position += self.knockback_direction * self.knockback_intensity * time.dt
            self.knockback_intensity -= 20 * time.dt

            # 3. רדיפה (רק אם חי)
        if self.hp > 0:
            z_dist = distance(self.position, player.position)
            if z_dist < 15:
                # הזומבי מסתכל על השחקן אבל שומר על ציר ה-Y ישר (שלא יתהפך)
                old_y = self.y
                self.look_at(player)
                self.rotation_x = 0
                self.rotation_z = 0
                self.position += self.forward * 2 * time.dt
                self.y = old_y  # מוודא שהתנועה קדימה לא מבטלת את הנפילה

                if z_dist < 1.5:
                    player.hp -= 10 * time.dt
                    update_health_ui()
                    if not damage_sound.playing:
                        damage_sound.play()
                        invoke(damage_sound.stop, delay=1)



# --- Spawning System ---
def spawn_zombie():
    # יוצר זומבי במיקום אקראי על המפה (בין 0 ל-15)
    x = random.uniform(0, 15)
    z = random.uniform(0, 15)
    Zombie(position=(x, 1, z))
    # קורא לעצמו שוב בעוד 10 שניות
    invoke(spawn_zombie, delay=10)


# --- UI & Entities ---
hand = Entity(parent=camera.ui, model='cube', texture=BLOCK_TYPES[0]['texture'],
              scale=(0.2, 0.2, 0.8), position=(0.35, -0.6), rotation=(150, -10, 0), color=color.white)

hotbar_slots = []
for i, block in enumerate(BLOCK_TYPES):
    slot = Entity(parent=camera.ui, model='quad', texture=block['texture'],
                  color=block['color'], scale=(0.08, 0.08), position=(-0.15 + (i * 0.1), -0.45), z=0)
    hotbar_slots.append(slot)

selector = Entity(parent=camera.ui, model='quad', color=color.rgba(255, 255, 0, 0.5),
                  scale=(0.09, 0.09), position=hotbar_slots[0].position, z=-1)


# --- Logic Functions ---

def update_hotbar():
    selector.position = hotbar_slots[selected_index].position
    hand.texture = BLOCK_TYPES[selected_index]['texture']
    hand.color = BLOCK_TYPES[selected_index]['color']


class Voxel(Button):
    def __init__(self, position=(0, 0, 0), block_type_index=0):
        super().__init__(
            parent=scene, position=position, model='cube', origin_y=0.5,
            texture=BLOCK_TYPES[block_type_index]['texture'],
            color=BLOCK_TYPES[block_type_index]['color'],
            highlight_color=BLOCK_TYPES[block_type_index]['color']
        )
        self.block_type_index = block_type_index


def stop_mining():
    global current_block, break_timer
    if current_block and isinstance(current_block, Voxel):
        current_block.color = BLOCK_TYPES[current_block.block_type_index]['color']
        current_block.rotation = (0, 0, 0)
    current_block = None
    break_timer = 0
    hit_sound.stop()


def input(key):
    global selected_index
    if key in ['1', '2', '3', '4', '5']:
        selected_index = int(key) - 1
        update_hotbar()

    if key == 'e':
        mouse.locked = not mouse.locked
        inventory.visible = not inventory.visible
        add_item_button.visible = inventory.visible

    if key == 'left mouse down':
        if mouse.hovered_entity and isinstance(mouse.hovered_entity, Zombie):
            if distance(mouse.hovered_entity.position, player.position) < 4:
                # שליחת מיקום השחקן לצורך חישוב כיוון הרתע
                mouse.hovered_entity.take_damage(20, knock_from=player.world_position)

    if key == 'left mouse up':
        stop_mining()

    if key =='f':
        if background_sound.playing:
            background_sound.stop()
        else:
            background_sound.play()



def update():
    global break_timer, current_block, place_cooldown, last_safe_position, last_hovered

    if last_hovered and last_hovered != current_block:
        if isinstance(last_hovered, Voxel):
            last_hovered.color = BLOCK_TYPES[last_hovered.block_type_index]['color']
        last_hovered = None

    if mouse.hovered_entity and isinstance(mouse.hovered_entity, Voxel):
        if distance(mouse.hovered_entity.position, player.position) < reach_distance:
            last_hovered = mouse.hovered_entity
            if last_hovered != current_block:
                last_hovered.color = color.rgba(255, 255, 0, 128)

    ground_check = raycast(player.position + Vec3(0, 0.1, 0), Vec3(0, -1, 0), distance=1.1, ignore=(player,))
    if ground_check.hit:
        last_safe_position = player.position

    # --- זיהוי מים ---
    in_water = False
    for water_block in [e for e in scene.entities if isinstance(e, Water)]:
        if distance(water_block.position, player.position) < 1.2:
            in_water = True
            break

    if in_water:
        player.speed = 2
        if held_keys['space']:
            player.y += 3 * time.dt
            player.fall_start_y = player.y
    else:
        if held_keys['control']:
            player.speed = 9
            player.camera_pivot.y = 2
        elif held_keys['shift']:
            player.speed = 2.5
            player.camera_pivot.y = 1.6
            if not ground_check.hit:
                player.position = last_safe_position
        else:
            player.speed = 5
            player.camera_pivot.y = 2

    # Placing
    if held_keys['right mouse'] and not inventory.visible:
        place_cooldown -= time.dt
        if place_cooldown <= 0:
            if mouse.hovered_entity and distance(mouse.hovered_entity.position, player.position) < reach_distance:
                new_pos = mouse.hovered_entity.position + mouse.normal
                on_column = abs(player.x - new_pos.x) < 0.7 and abs(player.z - new_pos.z) < 0.7
                in_height = new_pos.y > player.y - 0.5 and new_pos.y < player.y + 1.6
                if not (on_column and in_height):
                    Voxel(position=new_pos, block_type_index=selected_index)
                    hand.animate_position((0.4, -0.55), duration=0.05)
                    hand.animate_position((0.35, -0.6), duration=0.05, delay=0.05)
                    place_cooldown = 0.35
    else:
        place_cooldown = 0

    # Breaking
    if held_keys['left mouse'] and not inventory.visible:
        hand.position = (0.35, -0.55)
        hand.rotation_x = 140 + sin(time.time() * 15) * 10
        if not current_block:
            if mouse.hovered_entity and isinstance(mouse.hovered_entity, Voxel):
                if distance(mouse.hovered_entity.position, player.position) < reach_distance:
                    current_block = mouse.hovered_entity
                    if not hit_sound.playing: hit_sound.play()
        if current_block:
            if mouse.hovered_entity != current_block:
                stop_mining()
            else:
                b_info = BLOCK_TYPES[current_block.block_type_index]
                break_timer += time.dt
                current_block.color = lerp(b_info['color'], color.red, break_timer / b_info['break_time'])
                if break_timer >= b_info['break_time']:
                    destroy(current_block)
                    stop_mining()
    else:
        hand.rotation_x = 150 + sin(time.time() * 2) * 2

    if not ground_check.hit:
        if player.y > player.fall_start_y:
            player.fall_start_y = player.y
    else:
        fall_distance = player.fall_start_y - player.y
        if fall_distance > 4:
            player.hp -= int(fall_distance * 5)
            update_health_ui()
            camera.shake(duration=0.2, magnitude=2)
            damage_sound.play()
            invoke(damage_sound.stop, delay=1)
        player.fall_start_y = player.y

    if player.hp <= 0 or player.y <= -10:
        respawn_player()



def respawn_player():
    player.position = (8, 0, 8)
    player.hp = 100
    player.fall_start_y = 2
    update_health_ui()
    respawn_sound.play()



# --- Inventory ---
class Inventory(Entity):
    def __init__(self, width=5, height=2):
        super().__init__(parent=camera.ui, model='quad', scale=(width * 0.1, height * 0.1),
                         origin=(-0.5, 0.5), position=(-0.25, 0.25), color=color.black66, visible=False)
        self.width, self.height, self.slots = width, height, []

    def append(self, item_texture):
        item = Draggable(parent=self, model='quad', texture=item_texture, scale=(1 / 5, 1 / 2), origin=(-0.5, 0.5))
        self.slots.append(item)


inventory = Inventory()
add_item_button = Button(scale=.1, x=-.5, color=color.lime, text='+', on_click=lambda: inventory.append('grass'),
                         visible=False)

player = FirstPersonController()
Sky()

# התחלת מערכת ה-Spawning
spawn_zombie()

player.hp = 100
player.max_hp = 100
player.fall_start_y = player.y

health_bar_bg = Entity(parent=camera.ui, model='quad', color=color.black66, scale=(0.4, 0.02), position=(0, -0.4))
health_bar = Entity(parent=health_bar_bg, model='quad', color=color.red, scale=(1, 1), origin=(-0.5, 0), x=-0.5)


def update_health_ui():
    health_bar.scale_x = player.hp / player.max_hp


class Water(Entity):
    def __init__(self, position=(0, 0, 0)):
        super().__init__(parent=scene, position=position, model='cube', texture='white_cube',
                         color=color.rgba(0, 100, 255, 150), collider='box', origin_y=0.5)
        self.collision = False


for z in range(16):
    for x in range(16): Voxel(position=(x, 0, z))
for z in range(5, 8):
    for x in range(5, 8): Water(position=(x, 1, z))

app.run()