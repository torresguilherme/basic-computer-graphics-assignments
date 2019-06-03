import argparse
import math
import time
import multiprocessing
import random

PIXEL_SIZE = 0.01
DISTRIBUTED_RAYS = 4
VISION_RANGE = 2 ** 63 - 1
CPUS = multiprocessing.cpu_count() * 2
OBJ_NEAR = 0.0005

#######################################
### AUXILIARY
#######################################

def schlick(cosine, ref_idx):
    r0 = (1-ref_idx) / (1+ref_idx)
    r0 = r0 * r0
    return r0 + (1-r0) * math.pow((1 - cosine), 5)

def mean(array):
    sum = 0
    for item in array:
        sum += item
    return sum / len(array)

#######################################
### MATH PRIMITIVES
#######################################

class Vec3:
    def __init__(self, *args):
        if len(args) == 3:
            self.x = args[0]
            self.y = args[1]
            self.z = args[2]
        else:
            self.x = 0
            self.y = 0
            self.z = 0
    
    def __str__(self):
        return '(' + str(self.x) + ', ' + str(self.y) + ', ' + str(self.z) + ')'
    
    def __getitem__(self, key):
        if key is 0:
            return self.x
        elif key is 1:
            return self.y
        elif key is 2:
            return self.z
        else:
            raise IndexError('Vec3 index must be in range, not ' + key)
    
    def __setitem__(self, key, value):
        if key is 0:
            self.x = value
        elif key is 1:
            self.y = value
        elif key is 2:
            self.z = value
        else:
            raise IndexError('Vec3 index must be in range, not ' + key)
    
    def __neg__(self):
        return Vec3(-self.x, -self.y, -self.z)

    def __add__(self, other):
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)
    
    def __sub__(self, other):
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)
    
    def __iadd__(self, other):
        return self + other
    
    def __isub__(self, other):
        return self - other
    
    def __mul__(self, scalar):
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)
    
    def __imul__(self, scalar):
        return self * scalar

    def __truediv__(self, scalar):
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)
    
    def __trueidiv__(self, scalar):
        return self / scalar
    
    def array(self):
        return [self.x, self.y, self.z]
    
    def dot(self, other):
        return self.x * other.x + self.y * other.y + self.z * other.z
    
    def cross(self, other):
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.x * other.z - self.z * other.x,
            self.x * other.y - self.y * other.x
        )
    
    def euclid_distance(self, other):
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)
    
    def reflect(self, normal):
        return self - (normal * 2 * self.dot(normal))
    
    def refract(self, normal, ni_over_nt):
        unit_v = self.normalize()
        cosine = unit_v.dot(normal)
        discriminant = 1 - ni_over_nt * ni_over_nt * (1 - cosine * cosine)
        if(discriminant > 0):
            refracted_vec = (unit_v - normal * cosine) * ni_over_nt - normal * math.sqrt(discriminant)
            return refracted_vec
        return self.reflect(normal)

    def lenght(self):
        return math.sqrt(self.dot(self))
    
    def normalize(self):
        try:
            return Vec3(self.x / self.lenght(), self.y / self.lenght(), self.z / self.lenght())
        except ZeroDivisionError:
            return Vec3()

class Ray:
    def __init__(self, *args):
        if len(args) == 2:
            self.start = args[0]
            self.direction = args[1].normalize()
        else:
            self.start = Vec3()
            self.direction = Vec3()
    
    def __str__(self):
        return 'Start: ' + str(self.start) + ' Direction: ' + str(self.direction)

    def point_at_t(self, t):
        return self.start + self.direction * t

#######################################
### ILLUMINATION PRIMITIVES
#######################################

class PointLight:
    def __init__(self, position, color):
        self.position = position
        self.color = color
    
    def __str__(self):
        return 'Light position: ' + str(self.position) + ' Color: ' + str(self.color)

class Material:
    def __init__(self, **kwargs):
        self.type = kwargs.get('type')
        self.albedo = kwargs.get('albedo')
        try:
            self.emission = kwargs.get('emission')
        except:
            self.emission = Vec3()
        if self.type == 'dielectric':
            # cover glass/dielectric materials
            self.k_refraction = kwargs.get('k_refraction')
            self.k_attenuation = kwargs.get('k_attenuation')
        elif self.type == 'reflective':
            # cover metal/reflective material parameters
            self.k_reflectance = kwargs.get('k_reflectance')
            self.fuzz = kwargs.get('fuzz')
        elif self.type == 'phong':
            # cover phong material parameters
            self.shading = kwargs.get('shading')
            self.k_specular = kwargs.get('k_specular')
        else:
            self.type = 'lambert'
            self.k_diffuse = kwargs.get('k_diffuse')
    
    def __str__(self):
        return 'Type: ' + self.type + ' Albedo: ' +  str(self.albedo)

#######################################
### SHAPE PRIMITIVES
#######################################

class Sphere:
    def __init__(self, center, radius, material):
        self.center = center
        self.radius = radius
        self.material = material
    
    def __str__(self):
        return 'Type of shape: sphere. Center: ' + str(self.center) + ' Radius: ' + str(self.radius) + '\nMaterial:\n\t' + str(self.material)
    
    def normal(self, point):
        return (point - self.center).normalize()

class Mesh:
    def __init__(self, file_name, material):
        self.material = material
        self.vertices = []
        self.faces = []
        self.uvs = []
        self.vertex_normals = []

        # loading obj

#######################################
### RAY INTERSECT HANDLING
#######################################

def trace_rays_in_row(shapes, point_lights, i, width, height, camera_eye, camera_up, camera_right, camera_front, focal_dist, array):
    for j in range(width):
        result = trace_rays(shapes, point_lights, i, j, width, height, camera_eye, camera_up, camera_right, camera_front, focal_dist)
        for k in range(3):
            array[i * width * 3 + j * 3 + k] = int(math.floor(result[k]))

def trace_rays(shapes, point_lights, i, j, width, height, camera_eye, camera_up, camera_right, camera_front, focal_dist):
    ipc = camera_eye + camera_front * focal_dist
    colors = []
    sqrt = math.sqrt
    for k in range(DISTRIBUTED_RAYS):
        sqrt_dist_rays = sqrt(DISTRIBUTED_RAYS)
        sampling_offset = (sqrt_dist_rays - (k % sqrt_dist_rays / sqrt_dist_rays), \
                            sqrt_dist_rays - (k / sqrt_dist_rays / sqrt_dist_rays))
        # ray = eye + t * (pixel_pos - eye)
        pixel_pos = ipc + (camera_right * (j - width/2 + sampling_offset[0]) + camera_up * (height/2 - i + sampling_offset[1])) * PIXEL_SIZE
        ray = Ray(camera_eye, pixel_pos - camera_eye)
        
        params = []
        for s in shapes:
            params.append(intersects(ray, s, shapes))
        
        min_t = VISION_RANGE
        color = Vec3(0, 0, 0)
        for p in params:
            if p[0] >= OBJ_NEAR and p[0] < min_t:
                color = p[1]
                min_t = p[0]

        if color != Vec3(0, 0, 0):
            occlusions = []
            for light in point_lights:
                occlusions.append(occlusion(ray, min_t, shapes, light))
            color *= mean(occlusions)
        colors.append(color)

    # retorna media das cores
    average = [0, 0, 0]
    for k in range(DISTRIBUTED_RAYS):
        for l in range(3):
            average[l] += colors[k][l]
    for k in range(3):
        average[k] /= DISTRIBUTED_RAYS
    return average

def intersects(ray, shape, other_shapes, occlusion=False):
    # intersect with sphere
    try:
        oc = ray.start - shape.center
        a = ray.direction.dot(ray.direction)
        b = 2 * oc.dot(ray.direction)
        c = oc.dot(oc) - shape.radius * shape.radius
        discriminant = b * b - 4 * a * c
        if discriminant > OBJ_NEAR:
            sqrt = math.sqrt
            s1 = (-b - sqrt(discriminant))/ (2 * a)
            s2 = (-b + sqrt(discriminant))/ (2 * a)
            solution = min(s1, s2)
            #solution = (-b - sqrt(discriminant))/ (2 * a)
            if occlusion:
                return solution
            try:
                shape.material.k_diffuse
                # cover lambertian materials
                return solution, shape.material.albedo * shape.material.k_diffuse + shape.material.emission
            except AttributeError:
                pass
            try:
                shape.material.k_reflectance
                # cover reflective materials
                reflected_ray = Ray(ray.point_at_t(solution),
                    ray.direction.reflect(shape.normal(ray.point_at_t(solution))) \
                    + Vec3(random.random(), random.random(), random.random()) * shape.material.fuzz)
                hits = []
                other_shapes_real = [x for x in other_shapes if x != shape]
                for s in other_shapes_real:
                    reflected_intersection = intersects(reflected_ray, s, other_shapes_real)
                    if reflected_intersection[0] > OBJ_NEAR:
                        hits.append(reflected_intersection)
                hits.sort(key=lambda val: val[0])
                try:
                    return solution, hits[0][1] * shape.material.k_reflectance + \
                            shape.material.albedo * (1 - shape.material.k_reflectance) + \
                            shape.material.emission
                except IndexError:
                    return solution, Vec3() * shape.material.k_reflectance + \
                            shape.material.albedo * (1 - shape.material.k_reflectance) + \
                            shape.material.emission
            except AttributeError:
                pass
            try:
                shape.material.k_attenuation
                # cover dielectric materials
                refracted_ray = Ray(ray.point_at_t(solution),
                    ray.direction.refract(shape.normal(ray.point_at_t(solution)), 1/shape.material.k_refraction))
                    #+ Vec3(1, 1, 1) * random.random() * shape.material.fuzz)
                hits = []
                other_shapes_real = [x for x in other_shapes if x != shape]
                for s in other_shapes_real:
                    refracted_intersection = intersects(refracted_ray, s, other_shapes_real)
                    if refracted_intersection[0] > OBJ_NEAR:
                        hits.append(refracted_intersection)
                hits.sort(key=lambda val: val[0])
                try:
                    return solution, hits[0][1] * shape.material.k_attenuation + \
                            shape.material.albedo * (1 - shape.material.k_attenuation) + \
                            shape.material.emission
                except IndexError:
                    return solution, Vec3() * shape.material.k_attenuation + \
                            shape.material.albedo * (1 - shape.material.k_attenuation) + \
                            shape.material.emission
            except AttributeError:
                pass
        else:
            if occlusion:
                return -1
            return -1, Vec3()
    except AttributeError:
        pass
    
    # intersect with triangle

    if occlusion:
        return -1
    return -1, Vec3(0, 0, 0)

def occlusion(ray, point_of_intersection, shapes, light):
    k_occlusions = []
    ray_to_light = Ray(ray.point_at_t(point_of_intersection), light.position - ray.point_at_t(point_of_intersection))
    for shape in shapes:
        if intersects(ray_to_light, shape, shapes, occlusion=True) > OBJ_NEAR:
            k_occlusions.append(0)
        else:
            k_occlusions.append(1 + ray_to_light.direction.dot(ray.direction))
    return mean(k_occlusions)

#######################################
### MAIN
#######################################

def main():
    # pegar arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('output_file', type=str, help='arquivo de saida')
    parser.add_argument('-width', type=int, help='largura do arquivo de saida')
    parser.add_argument('-height', type=int, help='altura do arquivo de saida')

    args = parser.parse_args()
    ouf = args.output_file
    width = 480
    height = 340
    if args.width:
        width = args.width
    if args.height:
        height = args.height
    
    # camera parameters
    camera_eye = Vec3(0, 0, 0)
    focal_dist = PIXEL_SIZE * 100
    camera_target = Vec3(0, 0, 5)
    camera_up = Vec3(0, 1, 0)
    camera_front = (camera_target - camera_eye).normalize()
    camera_right = camera_up.cross(camera_front).normalize()
    camera_up = camera_right.cross(camera_front)
    print(camera_eye, camera_front, camera_right, camera_up)

    # get shapes
    shapes = []
    ground_material = Material(type='lambert', albedo=Vec3(0, 255, 150), k_diffuse=0.8)
    ball_material = Material(type='lambert', albedo=Vec3(255, 0, 0), k_diffuse=0.9)
    glass_material = Material(type='dielectric', albedo=Vec3(0, 150, 125), k_refraction=1.7, k_attenuation=0.5)
    gold_material = Material(type='reflective', albedo=Vec3(200, 200, 0), k_reflectance=0.4, fuzz=0.7)
    sky = Material(type='lambert', emission=Vec3(150, 150, 255), albedo=Vec3(150, 150, 255), k_diffuse=0.9)
    shapes.append(Sphere(Vec3(0, -100, 20), 100, ground_material))
    shapes.append(Sphere(Vec3(0, 0, 5), 1, ball_material))
    shapes.append(Sphere(Vec3(-2.5, 0, 4.5), 1, glass_material))
    shapes.append(Sphere(Vec3(2.5, 0, 4.5), 1, gold_material))
    shapes.append(Sphere(Vec3(0, 0, 0), 300, sky))

    # get lights
    point_lights = [PointLight(Vec3(3, 3, 3), Vec3(255, 255, 255))]
    
    # render image
    start_time = time.time()
    array = multiprocessing.Array('i', height * width * 3, lock=False)

    processes = [None] * CPUS
    for i in range(0, height, CPUS):
        for k in range(CPUS):
            if i + k < height:
                processes[k] = multiprocessing.Process(target=trace_rays_in_row, \
                    args=(shapes, point_lights, i + k, width, height, camera_eye, \
                    camera_up, camera_right, camera_front, focal_dist, array))
                processes[k].start()
        
        for p in processes:
            p.join()

    '''
    for i in range(height):
        for j in range(width):
            trace_rays(shapes, point_lights, i, j, width, height, \
                        camera_eye, camera_up, camera_right, camera_front, focal_dist, pixel_array[i][j])
    '''
    end_time = time.time() - start_time
    print('Imagem renderizada em ' + str(end_time) + ' segundos')

    # output img
    with open(ouf, 'w') as f:
        f.write('P3\n' + str(width) + ' ' + str(height) + '\n255\n')
        for byte in array:
            f.write(str(byte) + ' ')

    return 0

if __name__ == '__main__':
    main()