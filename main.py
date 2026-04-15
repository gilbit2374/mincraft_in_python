from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from direct.actor.Actor import Actor
import random

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

ARMOR_TYPES = [
    {
        'name': 'diamond_chestplate',
        'material': 'diamond',
        'type': 'chestplate',
        'texture': 'diamond_chestplate_2.png',
        'protection': 5,
        'durability': 50,
        'color': color.cyan
    }
]



# Global Variables
selected_index = 0
current_block = None
break_timer = 0
place_cooldown = 0
last_safe_position = Vec3(0, 0, 0)
reach_distance = 7
last_hovered = None
current_item = None

# Audio
hit_sound = Audio('mine-stone-with-a-pickaxe-333694.mp3', loop=False, autoplay=False)
respawn_sound = Audio('item_respawn-91422.mp3', loop=False, autoplay=False)
damage_sound = Audio('suffering-damage-284365.mp3', loop=False, autoplay=False)
background_sound = Audio('background-music-224633.mp3', loop=True, autoplay=True)


# --- ZOMBIE CLASS (FIXED) ---
class Zombie(Entity):
    def __init__(self, position=(0, 1, 0)):
        super().__init__(
            position=position,
            model=None,
            collider='box'
        )

        # 1. Physics & Stats
        self.collider = BoxCollider(self, center=Vec3(0, 1, 0), size=Vec3(1, 2, 1))
        self.hp = 100
        self.max_hp = 100
        self.knockback_direction = Vec3(0, 0, 0)
        self.knockback_intensity = 0
        self.fall_speed = 0
        self.old_position = self.position

        # This variable fixes the animation stuttering
        self.is_moving = False

        # 2. Load the 3D Model
        try:
            # IMPORTANT: Make sure your file is named 'zombie.glb' in the folder
            self.actor = Actor('zombie.glb.gltf')
            self.actor.reparent_to(self)

            # Scale and Texture
            self.actor.scale = 1  # If too big, change to 0.1. If too small, change to 5.
            self.actor.y = 0  # Align feet to floor

            zombie_tex = load_texture('zombie.png')
            if zombie_tex:
                self.actor.set_texture(zombie_tex, 1)

            # Start Idle Animation
            self.actor.loop("all_the_time")
            print("Zombie Model Loaded Successfully!")

        except Exception as e:
            # If you see the Green Block, look at the Console for this error message!
            print(f"ZOMBIE FAILED TO LOAD: {e}")
            self.actor = Entity(parent=self, model='cube', color=color.green, scale=(0.8, 1.8, 0.8), y=1)

        # 3. Health Bar
        self.health_bar_bg = Entity(parent=self, model='quad', color=color.black,
                                    scale=(1.2, 0.1), position=(0, 2.2, 0), billboard=True)
        self.health_bar = Entity(parent=self.health_bar_bg, model='quad', color=color.red,
                                 scale=(1, 1), position=(0, 0, -0.01), origin_x=-0.5, x=-0.5)

    def update_hp_bar(self):
        if hasattr(self, 'health_bar'):
            self.health_bar.scale_x = max(0, self.hp / self.max_hp)

    def take_damage(self, amount, knock_from=None):
        self.hp -= amount
        self.update_hp_bar()

        if not damage_sound.playing:
            damage_sound.play()
            invoke(damage_sound.stop, delay=1)

        if knock_from is not None:
            diff = self.world_position - knock_from
            self.knockback_direction = Vec3(diff.x, 0, diff.z).normalized()
            self.knockback_intensity = 10

        # Flash Red effect
        if hasattr(self, 'actor'):
            original_color = self.actor.color
            self.actor.color = color.red
            invoke(setattr, self.actor, 'color', original_color, delay=0.1)

        if self.hp <= 0:
            destroy(self)

    def update(self):
        # 1. GRAVITY
        ray = raycast(self.world_position + Vec3(0, 0.5, 0), Vec3(0, -1, 0), distance=0.6, ignore=(self,))

        if not ray.hit:
            self.fall_speed += 20 * time.dt
            self.y -= self.fall_speed * time.dt
        else:
            self.fall_speed = 0
            if self.y < ray.point.y:
                self.y = ray.point.y

        # 2. KNOCKBACK
        if self.knockback_intensity > 0:
            move_dir = self.knockback_direction
            wall_check = raycast(self.world_position + Vec3(0, 1, 0), move_dir, distance=1, ignore=(self,))
            if not wall_check.hit:
                self.position += move_dir * self.knockback_intensity * time.dt
            self.knockback_intensity -= 25 * time.dt

        # 3. CHASE & ANIMATION LOGIC
        if self.knockback_intensity <= 0:
            dist = distance(self.position, player.position)

            # Chase Logic
            if 1.5 < dist < 20:
                self.look_at(player)
                self.rotation_x = 0
                self.rotation_z = 0
                front_check = raycast(self.world_position + Vec3(0, 1, 0), self.forward, distance=1, ignore=(self,))
                if not front_check.hit:
                    self.position += self.forward * 2 * time.dt
            elif dist <= 1.5:
                hit_player(self, 400 * time.dt)

        # 4. ANIMATION STATE MACHINE (This fixes the stuttering)
        # Check if we moved since the last frame
        is_moving_now = (self.position != self.old_position)

        # Only switch animations if the state changed
        if isinstance(self.actor, Actor):
            if is_moving_now and not self.is_moving:
                self.actor.loop('moving')  # Switch to walk
                self.is_moving = True
            elif not is_moving_now and self.is_moving:
                self.actor.loop('all_the_time')  # Switch to idle
                self.is_moving = False

        self.old_position = self.position



# --- Spawning System ---
def spawn_zombie():
    x = random.uniform(0, 15)
    z = random.uniform(0, 15)
    Zombie(position=(x, 5, z))
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

    # Hotbar selection
    if key in ['1', '2', '3', '4', '5']:
        selected_index = int(key) - 1
        update_hotbar()

    # Toggle Inventory correctly
    if key == 'e':
        inventory.visible = not inventory.visible
        # The mouse should be UNLOCKED when inventory is VISIBLE
        mouse.locked = not inventory.visible
        add_item_button.visible = inventory.visible

    # Combat
    if key == 'left mouse down':
        if mouse.hovered_entity and isinstance(mouse.hovered_entity, Zombie):
            if distance(mouse.hovered_entity.position, player.position) < 4:
                mouse.hovered_entity.take_damage(20, knock_from=player.world_position)

    if key == 'left mouse up':
        stop_mining()

    # Music and Spawning
    if key == 'f':
        if background_sound.playing:
            background_sound.stop()
        else:
            background_sound.play()

    if key == 'c':
        spawn_zombie()

class Armor:
    def __init__(self, material, type):
        armor_name = f"{material}_{type}"
        data = next((item for item in ARMOR_TYPES if item["name"] == armor_name), None)

        if data:
            self.name = data['name']
            self.material = data['material'] # This is used for the UI text
            self.type = data['type']
            self.texture = data['texture']
            self.protection = data['protection']
            self.durability = data['durability']
            self.color = data.get('color', color.cyan)
        else:
            print(f"Error: Armor {armor_name} not found!")
            self.material = "None" # Fallback
            self.type = type
            self.protection = 0



def update():
    global break_timer, current_block, place_cooldown, last_safe_position, last_hovered,current_item

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

    # --- Water Logic ---
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

    if player.knockback_intensity > 0:
        check = raycast(player.world_position + Vec3(0, 1, 0), player.knockback_direction, distance=1, ignore=(player,))
        if not check.hit:
            player.position += player.knockback_direction * player.knockback_intensity * time.dt
        player.knockback_intensity -= 75 * time.dt
        if player.knockback_intensity < 0:
            player.knockback_intensity = 0

    current_item = BLOCK_TYPES[selected_index]['name']


def respawn_player():
    player.position = (8, 0, 8)
    player.hp = 100
    player.fall_start_y = 2
    update_health_ui()
    respawn_sound.play()


# --- Inventory ---
class InventoryItem(Draggable):
    def __init__(self, parent_inv, texture, armor_object=None):
        super().__init__(
            parent=parent_inv,
            model='quad',
            texture=texture,
            scale=(1 / 5, 1 / 2),
            origin=(-0.5, 0.5)
        )
        self.armor_object = armor_object  # Stores the armor stats (if it is armor)

    def input(self, key):
        if self.hovered and key == 'right mouse down':
            if self.armor_object is not None:
                slot = self.armor_object.type

                # OPTIONAL: If you're already wearing something, unequip it first
                if player.equipped_armor[slot]:
                    armor_ui.unequip_slot(slot)

                # Equip the new armor
                player.equipped_armor[slot] = self.armor_object

                # --- NEW: Refresh the UI ---
                armor_ui.refresh()

                destroy(self)


class Inventory(Entity):
    def __init__(self, width=5, height=2):
        super().__init__(parent=camera.ui, model='quad', scale=(width * 0.1, height * 0.1),
                         origin=(-0.5, 0.5), position=(-0.25, 0.25), color=color.black66, visible=False)
        self.width = width
        self.height = height
        self.slots = []

    # Updated append to accept armor data
    def append(self, item_texture, armor_data=None):
        item = InventoryItem(self, item_texture, armor_data)
        self.slots.append(item)


inventory = Inventory()

# Create the actual armor object using your Armor class
test_chestplate = Armor("diamond", "chestplate")

# Button to give the player the armor in their inventory
add_item_button = Button(
    scale=.1,
    x=-.5,
    color=color.lime,
    text='+',
    visible=False,
    on_click=lambda: inventory.append(test_chestplate.texture, test_chestplate)
)


class ArmorDisplay(Entity):
    def __init__(self):
        super().__init__(parent=camera.ui, position=(-0.85, 0.4))  # Top left
        self.labels = {}

        # Create a line for each slot
        slots = ['helmet', 'chestplate', 'leggings', 'boots']
        for i, slot in enumerate(slots):
            # The background button (Click this to unequip)
            btn = Button(
                parent=self,
                text=f"{slot.capitalize()}: None",
                scale=(0.25, 0.05),
                position=(0, -i * 0.06),
                color=color.black66,
                on_click=lambda s=slot: self.unequip_slot(s)
            )
            self.labels[slot] = btn

    def refresh(self):
        for slot, btn in self.labels.items():
            armor = player.equipped_armor[slot]
            if armor:
                btn.text = f"{slot.capitalize()}: {armor.material.capitalize()}"
                btn.color = armor.color if hasattr(armor, 'color') else color.azure
            else:
                btn.text = f"{slot.capitalize()}: None"
                btn.color = color.black66

    def unequip_slot(self, slot):
        armor = player.equipped_armor[slot]
        if armor:
            # 1. Put it back in inventory
            inventory.append(armor.texture, armor)
            # 2. Clear the player slot
            player.equipped_armor[slot] = None
            # 3. Update the screen
            self.refresh()
            print(f"Unequipped {slot}")


# Initialize it
armor_ui = ArmorDisplay()



player = FirstPersonController()
Sky()

#player armor initial
player.equipped_armor = {
    'helmet': None,
    'chestplate': None,
    'leggings': None,
    'boots': None
}

# 3.initialize the UI



# Initial Spawns
spawn_zombie()


#player initial stats
player.hp = 100
player.max_hp = 100
player.fall_start_y = player.y
player.knockback_direction = Vec3(0, 0, 0)
player.knockback_intensity = 0




#how to equip armor
#player.equipped_armor['chestplate'] = diamond_chest

health_bar_bg = Entity(parent=camera.ui, model='quad', color=color.black66, scale=(0.4, 0.02), position=(0, -0.4))
health_bar = Entity(parent=health_bar_bg, model='quad', color=color.red, scale=(1, 1), origin=(-0.5, 0), x=-0.5)


def update_health_ui():
    health_bar.scale_x = player.hp / player.max_hp


class Water(Entity):
    def __init__(self, position=(0, 0, 0)):
        super().__init__(parent=scene, position=position, model='cube', texture='white_cube',
                         color=color.rgba(0, 100, 255, 150), collider='box', origin_y=0.5)
        self.collision = False


def hit_player(source_entity, damage):
    #Calculate total protection from all worn armor
    total_protection = 0
    for armor_piece in player.equipped_armor.values():
        if armor_piece is not None:
            total_protection += armor_piece.protection

    #Subtract protection from the incoming damage
    actual_damage = damage - total_protection

    # Make sure damage doesn't heal the player if protection is higher!
    if actual_damage < 0:
        actual_damage = 0

    #Apply the damage
    player.hp -= actual_damage
    update_health_ui()

    #Apply Knockback
    diff = player.world_position - source_entity.world_position
    player.knockback_direction = Vec3(diff.x, 0, diff.z).normalized()
    player.knockback_intensity = 15-total_protection
    camera.shake(duration=0.1, magnitude=1)






# Generate World
for z in range(16):
    for x in range(16): Voxel(position=(x, 0, z))
for z in range(5, 8):
    for x in range(5, 8): Water(position=(x, 1, z))
app.run()