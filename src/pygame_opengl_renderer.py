import pygame
import OpenGL

# Switch on more debugging facilities
#OpenGL.FULL_LOGGING = True

import OpenGL.GL as GL
import math
import os
import os.path
import numpy
import re

from pymunk import Vec2d

from .renderer import *

class ShaderProgram(object):
    """ Manages an OpenGL shader program.

    Note that the program will currently never be deleted. My thinking
    is that there won't be many shaders, and so we will leave them to be
    cleaned up when the program terminates. """

    def __init__(self, shader_dir):
        """ Constructor - create and initialise a shader program.
        """

        # Note: see the following, which was referenced in the PyOpenGL
        # documentation:
        #       https://bitbucket.org/rndblnch/opengl-programmable/src/tip/10-g
        #       l3.2core.py?fileviewer=file-view-default

        # Create the program object.
        self.__shader_program = GL.glCreateProgram()

        # We're going to build up a list of inputs.
        program_uniforms = set()
        program_attributes = set()

        # Compile all of the source files and attach the resulting
        # shader objects to our shader program.
        for (filename, shader_type) in self.__list_shader_files(shader_dir):
            print (filename, shader_type)
            (file_uniforms, file_attributes) = self.__parse_uniforms_and_attributes(filename)
            print (file_uniforms, file_attributes)
            program_uniforms.update(file_uniforms);
            program_attributes.update(file_attributes);
            shader = GL.glCreateShader(shader_type)
            GL.glShaderSource(shader, open(filename, 'r').read())
            GL.glCompileShader(shader)
            if GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) != GL.GL_TRUE:
                raise Exception(GL.glGetShaderInfoLog(shader))
            GL.glAttachShader(self.__shader_program, shader)

        # Assign locations to vertex attributes. We'll bind them in the program later...
        self.__attrib_locations = dict((k, v) for (v, k) in enumerate(program_attributes))

        # Uniform locations will be determined by OpenGL, we'll get them later.
        self.__uniform_locations = {}

        # Now we can bind all of the vertex attributes to their
        # assigned locations.
        for attrib in program_attributes:
            GL.glBindAttribLocation(self.__shader_program,
                                    self.__attrib_locations[attrib],
                                    attrib)

        # Now link the program.
        GL.glLinkProgram(self.__shader_program)
        if GL.glGetProgramiv(self.__shader_program, GL.GL_LINK_STATUS) != GL.GL_TRUE:
            raise Exception(GL.glGetProgramInfoLog(self.__shader_program))

        # Retrieve the uniform locations and remember them.
        for uniform in program_uniforms:
            self.__uniform_locations[uniform] = GL.glGetUniformLocation(self.__shader_program, uniform)
            if self.__uniform_locations[uniform] == -1:
                print ("Warning: Uniform '%s' does not exist." % uniform)

    def __parse_uniforms_and_attributes(self, filename):
        """ Given a shader source file, return the names of attribute and
        uniform inputs. """
        uniforms = set()
        attributes = set()
        stream = open(filename, 'r')
        for line in stream:
            pattern = "(attribute|uniform) [a-zA-Z0-9_]+ ([a-zA-Z0-9_]+)"
            match = re.match(pattern, line)
            if match:
                storage_type = match.group(1)
                variable_name = match.group(2)
                if storage_type == "attribute":
                    attributes.add(variable_name)
                elif storage_type == "uniform":
                    uniforms.add(variable_name)
        return (uniforms, attributes)

    def __list_shader_files(self, dirname):
        """ List the shader files in a directory, inferring their types. """
        files = os.listdir(dirname)
        for filename in files:
            pattern = ".*\\.(v|f)\\.glsl$"
            match = re.match(pattern, filename)
            if match:
                type_str = match.group(1)
                type_enum = None
                if type_str == 'v':
                    type_enum = GL.GL_VERTEX_SHADER
                elif type_str == 'f':
                    type_enum = GL.GL_FRAGMENT_SHADER
                else:
                    continue
                yield (os.path.join(dirname, filename), type_enum)

    def begin(self):
        """ Render using the shader program. """
        GL.glUseProgram(self.__shader_program)

    def get_uniform_location(self, name):
        """ Get the location of a uniform. """
        if not name in self.__uniform_locations: return -1
        return self.__uniform_locations[name]

    def get_attribute_location(self, name):
        """ Get the location of an attribute. """
        if not name in self.__attrib_locations: return -1
        return self.__attrib_locations[name]

    def end(self):
        """ Render using the fixed function pipeline. """
        GL.glUseProgram(0)

class Texture(object):
    """ An OpenGL texture. """

    @classmethod
    def from_file(klass, filename):
        """ Create a texture from a file. """
        surface = pygame.image.load(filename).convert_alpha()
        return Texture(surface)

    @classmethod
    def from_surface(klass, surface):
        """ Create a texture from a surface. """
        return Texture(surface)

    def __init__(self, surface):
        """ Constructor. """
        data = pygame.image.tostring(surface, "RGBA", 1)
        self.__width = surface.get_width()
        self.__height = surface.get_height()
        self.__texture = GL.glGenTextures(1)
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.__texture)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, self.get_width(), self.get_height(),
                        0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, data)
        GL.glDisable(GL.GL_TEXTURE_2D)

    def begin(self):
        """ Set OpenGL state. """
        assert self.__texture is not None
        GL.glEnable(GL.GL_TEXTURE_2D)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.__texture)
        GL.glColor3f(1, 1, 1)

    def end(self):
        """ Unset the state. """
        assert self.__texture is not None
        GL.glDisable(GL.GL_TEXTURE_2D)

    def get_width(self):
        """ Get the texture width in pixels. """
        assert self.__texture is not None
        return self.__width

    def get_height(self):
        """ Get the texture height in pixels. """
        assert self.__texture is not None
        return self.__height

    def get_size(self):
        """ Get the texture size in pixels. """
        assert self.__texture is not None
        return (self.__width, self.__height)

    def delete(self):
        """ Free the texture. """
        if self.__texture is not None:
            GL.glDeleteTextures(self.__texture)
            self.__texture = None


class AnimFrames(object):
    """ A sequence of textures. """

    def __init__(self, texture_array, filenames):
        """ Constructor. """
        self.__texture_array = texture_array
        self.__filenames = filenames

    def get_size(self):
        """ The texture size. """
        return (self.get_width(), self.get_height())

    def get_width(self):
        """ The texture width. """
        return self.get_frame_by_index(0).get_width()

    def get_height(self):
        """ The texture height. """
        return self.get_frame_by_index(0).get_height()

    def get_frame_by_index(self, index):
        """ Get texture coordinates for the frame. """
        return self.__texture_array.lookup_texture(self.__filenames[index])

    def get_frame(self, timer):
        """ Get a frame from a timer. """
        idx = timer.pick_index(len(self.__filenames))
        return self.get_frame_by_index(idx)


class TextureRef(object):
    """ A reference to a location in a texture. """

    def __init__(self, u0, v0, u1, v1, level):
        """ Constructor. """
        self.__min = Vec2d(u0, v0)
        self.__max = Vec2d(u1, v1)
        self.__level = level

    def get_texcoord(self, i):
        """ 'i' corresponds to a rectangle corner, and is a number between 0 and 3. """
        if i == 0:
            return (self.__min[0], self.__min[1], self.__level)
        if i == 1:
            return (self.__max[0], self.__min[1], self.__level)
        if i == 2:
            return (self.__max[0], self.__max[1], self.__level)
        if i == 3:
            return (self.__min[0], self.__max[1], self.__level)
        raise Exception("Expected 0 <= i <= 3, got %s" % i)

    def get_size(self):
        """ Get the size of the texture section. """
        return self.__max - self.__min

    def get_width(self):
        """ Get the width of the texture section. """
        return self.get_size[0]

    def get_height(self):
        """ Get the height of the texture section. """
        return self.get_size[1]

    def get_level(self):
        """ Get the level of the texture section. """
        return self.__level


class TextureArray(object):
    """ A texture array for rendering many sprites without changing
    textures. """

    def __init__(self):
        self.__max_width = 0
        self.__max_height = 0
        self.__texture_dimensions = []
        self.__texture = 0
        self.__filename_indices = {}

    def load(self, files):

        # Read in each image file and determine the maximum extents,
        # remembering the extents of each one.
        self.__max_width = 0
        self.__max_height = 0
        self.__texture_dimensions = []
        images = []
        for (i, filename) in enumerate(files):
            self.__filename_indices[filename] = i
            surf = pygame.image.load(filename)
            self.__max_width = max(self.__max_width, surf.get_width())
            self.__max_height = max(self.__max_height, surf.get_height())
            self.__texture_dimensions.append(surf.get_size())
            images.append(surf)

        # Allocate the texture array.
        self.__texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D_ARRAY, self.__texture)
        GL.glTexImage3D(
            GL.GL_TEXTURE_2D_ARRAY,
            0, #level
            GL.GL_RGBA8, # internal format
            self.__max_width,
            self.__max_height,
            len(images),
            0, #border
            GL.GL_RGBA, # format
            GL.GL_UNSIGNED_BYTE, # data type
            None # The data.
        )

        # Upload each image to the array.
        for (i, image) in enumerate(images):
            image_bytes = pygame.image.tostring(image, "RGBA", 1)
            GL.glTexSubImage3D(
                GL.GL_TEXTURE_2D_ARRAY,
                0, # Mipmap number
                0, # x offset
                0, # y offset
                i, # z offset
                image.get_width(),
                image.get_height(),
                1, # Depth
                GL.GL_RGBA, # format
                GL.GL_UNSIGNED_BYTE, # data type
                image_bytes # data
            )

    def lookup_texture(self, filename):
        """ Lookup a texture in the atlas from its filename. """
        if not filename in self.__filename_indices:
            return TextureRef(0, 0, 0, 0, 0)
        index = self.__filename_indices[filename]
        dims = self.__texture_dimensions[index]
        return TextureRef(0, 0, dims[0], dims[1], index)

    def begin(self):
        """ Begin rendering with the texture array. """
        GL.glBindTexture(GL.GL_TEXTURE_2D_ARRAY, self.__texture)

    def end(self):
        """ Stop rendering with the texture array. """
        pass


class CommandBufferArray(object):
    """ Command buffer array - stores a set of command buffers and knows what
    buffer should be filled from a given job. """

    def __init__(self, shader_program, texture_array):
        """ Initialise the command buffer array. """
        self.__shader_program = shader_program
        self.__texture_array = texture_array
        self.__buffers = {}

    def get_buffer(self, coordinate_system, level, primitive_type):
        """ Get the buffer to add vertices to. """
        key = (level, coordinate_system, primitive_type)
        if key not in self.__buffers:
            self.__buffers[key] = CommandBuffer(
                coordinate_system,
                self.__shader_program,
                self.__texture_array,
                primitive_type
            )
        return self.__buffers[key]

    def reset(self, view):
        """ Reset the buffers so they can be re-used. """
        for key in self.__buffers:
            self.__buffers[key].reset(view)

    def dispatch(self):
        """ Dispatch commands to the GPU. """
        for key in sorted(self.__buffers.keys()):
            self.__buffers[key].dispatch()


class VertexData(object):
    """ A blob of vertex data. Each vertex can have a number of attributes. """

    def __init__(self, shader_program, attribute_formats, default_size=32):
        """ Initialise a vertex data block. """
        self.__shader_program = shader_program
        self.__arrays = {}
        self.__vbos = {}
        self.__sizes = {}
        self.__numpy_types = {}
        self.__n = 0
        self.__max = default_size
        for (name, size, data_type) in attribute_formats:
            self.__sizes[name] = size
            self.__arrays[name] = numpy.zeros(default_size * size, data_type)
            self.__vbos[name] = OpenGL.arrays.vbo.VBO(self.__arrays[name])
            self.__numpy_types[name] = data_type

    def reset(self):
        """ Reset the vertex data so it can be re-used. """
        self.__n = 0

    def add_vertex(self, **kwargs):
        """ Add a vertex. """

        # NOTE: Since this function is going to be called once per vertex
        # I should imagine it is going to be performance critical. The current
        # implementation not very efficient, looking up lots of string in
        # hash tables etc. Will probably need to optimise or do this in a
        # different way (e.g. specify more than one vertex at a time, have
        # calling code specify vertex components directly...)

        # Expand the buffer if necessary.
        if self.__n == self.__max:
            self.__max *= 2
            for name in self.__arrays:
                # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
                # NOTE: not doing refcheck here since it fails. I'm not sure
                # why, something in the vbo code must be creating a view onto
                # the array. This shuts up the exception, but it could mean
                # that the code is going to go horribly wrong. Dont try this
                # at home kids.
                #
                # Need to work out what the right thing to do here is.
                # * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
                self.__arrays[name].resize(self.__max * self.__sizes[name], refcheck=False)

        # Add the vertex attributes.
        for key in kwargs:
            if key in self.__arrays:
                data = kwargs[key]
                array = self.__arrays[key]
                size = self.__sizes[key]
                try:
                    # Try to interpret the data as a vector.
                    for (i, component) in enumerate(data):
                        array[self.__n*size+i] = component
                except TypeError:
                    # Ok, it's a scalar.
                    array[self.__n*size] = data

        # we've added a vertex.
        self.__n += 1

    def bind_attributes(self):
        """ Setup the vertex attributes for rendering. """

        # We store each attribute in its own buffer.
        for name in self.__vbos:

            # Get the attribute vbo.
            vbo = self.__vbos[name]

            # Update the array data, since it will change per-frame.
            vbo.set_array(self.__arrays[name])

            # Bind the vbo (this does also does some data wrangling I believe.)
            vbo.bind()

            # Switch on the attribute and describe the data format to OpenGL.
            GL.glEnableVertexAttribArray(self.__shader_program.get_attribute_location(name))
            gl_type = {'f': GL.GL_FLOAT}[self.__numpy_types[name]]
            GL.glVertexAttribPointer(self.__shader_program.get_attribute_location(name),
                                     self.__sizes[name], gl_type, GL.GL_FALSE, 0, None)

    def __len__(self):
        """ Return the number of vertices. """
        return self.__n


class CommandBuffer(object):
    """ A single draw call. """

    def __init__(self, coordinate_system, shader_program, texture_array, primitive_type):
        """ Constructor. """

        # Uniform state.
        self.__coordinate_system = coordinate_system
        self.__shader_program = shader_program
        self.__primitive_type = primitive_type
        self.__texture_array = texture_array
        self.__view_position = (0, 0)
        self.__view_size = (0, 0)
        self.__view_zoom = 1

        # Per-vertex data.
        self.__vertex_data = VertexData(self.__shader_program,
                                        (("position", 2, 'f'),
                                         ("texcoord", 3, 'f'),
                                         ("colour", 3, 'f'),
                                         ("orientation", 1, 'f'),
                                         ("origin", 2, 'f')))

    def reset(self, view):
        """ Reset the command buffer so we can re-use it. """
        self.__vertex_data.reset()
        self.__view_position = view.position
        self.__view_size = view.size
        self.__view_zoom = view.zoom

    def add_quad(self, position, size, **kwargs):
        """ Emit a quad. Note that we say quad, but we actually emit
        a pair of triangles since this type of geometry can be more
        easily batched. """

        # Dummy texref in case one hasn't been specified.
        texref=TextureRef(0, 0, 0, 0, 0)
        if "texref" in kwargs:
            texref = kwargs["texref"]

        # (0, 0) -------------------- (1, 0)
        #    |                          |
        #    |                          |
        #    |                          |
        # (0, 1) -------------------- (1, 1)

        # The four corners of a quad.
        w = size[0]
        h = size[1]
        tl = (-w/2, -h/2)
        tr = (w/2, -h/2)
        br = (w/2, h/2)
        bl = (-w/2, h/2)
        positions = (tl, tr, br, bl)

        # Emit the top left triangle.
        for i in (0, 1, 3):
            self.__vertex_data.add_vertex(origin=position,
                                          position=positions[i],
                                          texcoord=texref.get_texcoord(i),
                                          **kwargs)

        # Emit the bottom right triangle.
        for i in (3, 1, 2):
            self.__vertex_data.add_vertex(origin=position,
                                          position=positions[i],
                                          texcoord=texref.get_texcoord(i),
                                          **kwargs)

    def dispatch(self):
        """ Dispatch the command to the GPU. """

        # If there's nothing to do then avoid doing any work.
        if len(self.__vertex_data) == 0:
            return

        # Use the shader program.
        self.__shader_program.begin()

        # Use the texture array.
        self.__texture_array.begin()

        # Setup uniform data.
        GL.glUniform1i(self.__shader_program.get_uniform_location("coordinate_system"), self.__coordinate_system)
        GL.glUniform2f(self.__shader_program.get_uniform_location("view_position"), *self.__view_position)
        GL.glUniform2f(self.__shader_program.get_uniform_location("view_size"), *self.__view_size)
        GL.glUniform1f(self.__shader_program.get_uniform_location("view_zoom"), self.__view_zoom)

        # Specify vertex attributes.
        self.__vertex_data.bind_attributes()

        # Draw the quads.
        GL.glDrawArrays(self.__primitive_type, 0, len(self.__vertex_data))

        # Stop using the texture array.
        self.__texture_array.end()

        # Stop using the shader program.
        self.__shader_program.end()


class PygameOpenGLRenderer(Renderer):
    """ A pygame software renderer. """

    def __init__(self):
        """ Constructor. """
        Renderer.__init__(self)
        self.__surface = None
        self.__data_path = None
        self.__filenames = []
        self.__anim_shader = None
        self.__texture_array = TextureArray()
        self.__command_buffers = None

    def initialise(self, screen_size, data_path):
        """ Initialise the pygame display. """
        self.__surface = pygame.display.set_mode(screen_size, pygame.DOUBLEBUF|pygame.OPENGL)
        self.__data_path = data_path
        GL.glViewport(0, 0, self.__surface.get_width(), self.__surface.get_height())
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0, self.__surface.get_width(), self.__surface.get_height(), 0, 0, 1)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        print ("OpenGL version: %s" % GL.glGetString(GL.GL_VERSION))
        print ("OpenGL vendor: %s" % GL.glGetString(GL.GL_VENDOR))

        self.__anim_shader = ShaderProgram(os.path.join(self.__data_path, "shaders/anim"))

        # Initialise command buffers.  Jobs will be sorted by layer and coordinate system and added
        # to an appropriate command buffer for later dispatch.
        self.__command_buffers = CommandBufferArray(self.__anim_shader, self.__texture_array)

    def post_preload(self):
        """ Initialise the texture array. """
        self.__texture_array.load(self.__filenames)

    def render_jobs(self, view):
        """ Perform rendering. """

        # Reset command buffers
        self.__command_buffers.reset(view)

        # Clear the screen
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        # Visit each job to fill command buffers
        Renderer.render_jobs(self)

        # Dispatch commands to the GPU.
        self.__command_buffers.dispatch()

    def flip_buffers(self):
        """ Update the pygame display. """
        pygame.display.flip()

    def load_compatible_image(self, filename):
        """ Load a pygame image. """
        self.__filenames.append(filename)
        return Texture.from_file(filename)

    def load_compatible_anim_frames(self, filename_list):
        """ Load the frames of an animation into a format compatible
        with the renderer.  The implementation can return its own
        image representation; the client should treat it as an opaque
        object. """
        self.__filenames += filename_list
        return AnimFrames(self.__texture_array, filename_list)

    def load_compatible_font(self, filename, size):
        """ Load a pygame font. """
        return pygame.font.Font(filename, size)

    def compatible_image_from_text(self, text, font, colour):
        """ Create an image by rendering a text string. """
        return Texture.from_surface(font.render(text, True, colour))

    def screen_size(self):
        """ Get the display size. """
        return self.__surface.get_size()

    def screen_rect(self):
        """ Get the display size. """
        return self.__surface.get_rect()

    def render_RenderJobBackground(self, job):
        """ Render scrolling background. """
        pass
        #buffer = self.__command_buffers.get_buffer(job.coordinates, job.level, GL.GL_QUADS)
        #buffer.add_quad(job.position_lcs, job.image.get_size(), job.image)

    def render_RenderJobRect(self, job):
        """ Render rectangle. """
        buffer = self.__command_buffers.get_buffer(job.coords, job.level, GL.GL_TRIANGLES)
        buffer.add_quad(job.rect.center, job.rect.size, colour=job.colour)

    def render_RenderJobLine(self, job):
        """ Render a line. """
        pass
        #buffer = self.__command_buffers.get_buffer(job.coordinates, job.level, GL.GL_LINES)
        #buffer.add_lines((job.p0_lcs, job.p1_lcs), job.width, job.colour)

    def render_RenderJobLines(self, job):
        """ Render a polyline. """
        pass
        #buffer = self.__command_buffers.get_buffer(job.coordinates, job.level, GL.GL_LINES)
        #buffer.add_lines(job.points_lcs, job.width, job.colour)

    def render_RenderJobPolygon(self, job):
        """ Render a polygon. """
        pass
        #buffer = self.__command_buffers.get_buffer(job.coordinates, job.level, GL.GL_TRIANGLES)
        #buffer.add_triangulated_convex_polygon(job.points_lcs, job.colour)

    def render_RenderJobCircle(self, job):
        """ Render a circle. """
        #buffer = self.__command_buffers.get_buffer(job.coordinates, job.level, GL.GL_TRIANGLES)
        #buffer.add_quad() # Do circle in fragment shader.

    def render_RenderJobText(self, job):
        """ Render some text. """
        pass

    def render_RenderJobAnimation(self, job):
        """ Render an animation. """

        # Get command buffer to which to dispatch.
        buffer = self.__command_buffers.get_buffer(job.coords, job.level, GL.GL_TRIANGLES)

        # Get texture information about current animation frame.
        texref = job.anim.frames.get_frame(job.anim.timer)

        # Dispatch a quad to the command buffer.
        buffer.add_quad(job.position,
                        texref.get_size(),
                        texref=texref,
                        orientation=job.orientation)

    def render_RenderJobImage(self, job):
        """ Render an image. """
        #buffer = self.__command_buffers.get_buffer(job.coords, job.level, GL.GL_TRIANGLES)
        #buffer.add_quad(job.position,
        #                job.image.get_size(),
        #                texref=job.image)
        pass
